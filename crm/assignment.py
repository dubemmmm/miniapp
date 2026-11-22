"""
Lead assignment.

1. A lead for a property goes to that property's contact person
   (Property.contact_name, synced from Airtable's "Contact Name"), when that
   name matches an active, available agent.
2. Otherwise (no property, no contact name, no matching agent, or the agent is
   unavailable / on leave) fall back to the Weighted Least-Load algorithm:

Score(agent) = w1*(norm_open_leads) + w2*(norm_overdue_leads)
             - w3*(response_score) - w4*(location_match) - w5*(specialty_match)

The agent with the LOWEST score is selected.
Tie-break: oldest last_assigned_at, then lowest user.id.

Called inside a transaction.atomic() block with select_for_update() on UserProfile
to prevent concurrent double-assignments.
"""
from datetime import datetime, timezone as dt_timezone
from difflib import SequenceMatcher
from django.utils import timezone
from properties.models import UserProfile

# How close a contact name must be to an agent's name to count as the same
# person when there is no exact match (Airtable has "Ifunaya" / "Ifuanya" for
# the account "Ifunanya").
_CONTACT_FUZZY_THRESHOLD = 0.8


def _norm(value):
    return ' '.join((value or '').lower().split())


def match_contact_agent(contact_name, agents):
    """
    Return the agent (UserProfile) in `agents` that `contact_name` refers to, or None.

    Tries, in order: exact match on full name / first name / username, then the
    contact's first word against the same, then a close-spelling match. Returns
    None when nothing matches or when two agents match equally well.
    """
    contact = _norm(contact_name)
    if not contact:
        return None
    contact_first = contact.split()[0]

    def names(agent):
        user = agent.user
        full = _norm(user.get_full_name())
        out = {full, _norm(user.first_name), _norm(user.username)}
        if full:
            out.add(full.split()[0])
        out.discard('')
        return out

    agent_names = [(agent, names(agent)) for agent in agents]

    for probe in (contact, contact_first):
        hits = [agent for agent, ns in agent_names if probe in ns]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return None  # ambiguous (two agents share the name) — don't guess

    scored = sorted(
        (
            (max(SequenceMatcher(None, contact_first, n).ratio() for n in ns), agent)
            for agent, ns in agent_names if ns
        ),
        key=lambda x: -x[0],
    )
    if not scored or scored[0][0] < _CONTACT_FUZZY_THRESHOLD:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


def assign_agent(lead):
    """
    Determine the best eligible agent for the given lead.

    Returns a tuple:
        (UserProfile | None, score_snapshot dict, assignment_reason str)
    """
    from crm.models import SLAConfig

    sla_config = SLAConfig.get()

    today = timezone.now().date()

    # --- Eligible agents (row-locked for concurrency safety) ---
    eligible = list(
        UserProfile.objects.select_for_update()
        .filter(
            user__is_active=True,
            role='agent',
            is_available=True,
        )
        .exclude(on_leave_until__gte=today)
        .select_related('user')
    )

    if not eligible:
        return None, {}, 'FALLBACK'

    # --- The property's own contact person takes the lead, if we can find them ---
    contact_name = ''
    if lead.related_property_id:
        try:
            contact_name = lead.related_property.contact_name or ''
        except Exception:
            contact_name = ''
    contact_agent = match_contact_agent(contact_name, eligible)
    if contact_agent:
        return contact_agent, {
            'method': 'property_contact',
            'contact_name': contact_name.strip(),
            'winner_agent_id': contact_agent.user.id,
            'winner_agent_name': contact_agent.user.get_full_name() or contact_agent.user.username,
        }, 'PROPERTY_CONTACT'

    # --- Load the property's location + category for matching ---
    property_location = ''
    property_category = ''
    if lead.related_property_id:
        try:
            prop = lead.related_property
            property_location = (prop.address or '').lower()
            # Use luxury_status as a proxy for "category" in v1
            property_category = (prop.luxury_status or '').lower()
        except Exception:
            pass
    elif lead.property_location_snapshot:
        # Leads without a property (e.g. a curated-shortlist request from a
        # neighbourhood page) carry their market as the location snapshot, so
        # agents whose coverage_locations include that area still match.
        property_location = lead.property_location_snapshot.lower()

    # --- Compute raw metrics ---
    max_open = max((a.current_open_leads for a in eligible), default=0) or 1
    max_overdue = max((a.current_overdue_leads for a in eligible), default=0) or 1

    weights = {
        'w1': sla_config.w1_open_leads,
        'w2': sla_config.w2_overdue_leads,
        'w3': sla_config.w3_response_score,
        'w4': sla_config.w4_location_match,
        'w5': sla_config.w5_specialty_match,
    }

    scored = []
    for agent in eligible:
        norm_open = agent.current_open_leads / max_open
        norm_overdue = agent.current_overdue_leads / max_overdue
        response = agent.response_score  # already 0.0–1.0

        # Location match: does the property's address contain any of the agent's covered areas?
        location_match = 0.0
        if property_location and agent.coverage_locations:
            covered = [loc.strip().lower() for loc in agent.coverage_locations.split(',') if loc.strip()]
            if any(loc in property_location for loc in covered):
                location_match = 1.0

        # Specialty match
        specialty_match = 0.0
        if property_category and agent.property_specialties:
            specialties = [s.strip().lower() for s in agent.property_specialties.split(',') if s.strip()]
            if any(s in property_category for s in specialties):
                specialty_match = 1.0

        score = (
            weights['w1'] * norm_open
            + weights['w2'] * norm_overdue
            - weights['w3'] * response
            - weights['w4'] * location_match
            - weights['w5'] * specialty_match
        )

        scored.append({
            'agent': agent,
            'score': round(score, 6),
            'inputs': {
                'norm_open_leads': round(norm_open, 4),
                'norm_overdue_leads': round(norm_overdue, 4),
                'response_score': round(response, 4),
                'location_match': location_match,
                'specialty_match': specialty_match,
            },
        })

    # --- Sort: lowest score first; tie-break by oldest last_assigned_at, then lowest user.id ---
    scored.sort(key=lambda x: (
        round(x['score'], 3),
        x['agent'].last_assigned_at or datetime.min.replace(tzinfo=dt_timezone.utc),
        x['agent'].user.id,
    ))

    winner_entry = scored[0]
    winner = winner_entry['agent']

    snapshot = {
        'weights': weights,
        'max_open': max_open,
        'max_overdue': max_overdue,
        'property_location': property_location,
        'property_category': property_category,
        'all_agents': [
            {
                'agent_id': e['agent'].user.id,
                'agent_name': e['agent'].user.get_full_name(),
                'score': e['score'],
                **e['inputs'],
            }
            for e in scored
        ],
        'winner_agent_id': winner.user.id,
        'winner_score': winner_entry['score'],
        # Why the property's contact didn't get it (blank = property has none).
        'unmatched_contact_name': contact_name.strip(),
    }

    return winner, snapshot, 'SCORE_BASED'
