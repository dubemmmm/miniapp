/* Shared property-UI helpers used by the grid (temp-v3.js) and the map (dashboard-v3.js).
   Keeps the WhatsApp enquiry wording identical across surfaces (it had drifted before). */
window.CWCards = window.CWCards || {};

/** Build the prefilled WhatsApp enquiry text.
 *  Callers format their own price string (numeric on the grid, parsed-string on the map)
 *  and pass it in, so the wording stays in one place. */
window.CWCards.enquiryMessage = function ({ contactName, propertyName, location, priceStr, url }) {
  const name = contactName || 'there';
  const where = location ? ' in ' + location : '';
  return `Hi ${name}, I'm interested in ${propertyName}${where} listed at ${priceStr}. Please send me more details. ${url}`;
};
