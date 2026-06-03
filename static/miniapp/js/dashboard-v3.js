// dashboard.js

let map, properties = [], filteredProperties = [];
let currentImageIndex = 0;
let currencyConverter;
let selectedPropertyIds = new Set(); // Track selected properties for comparison

// Currency Converter Class
class CurrencyConverter {
    constructor() {
        this.currentCurrency = 'NGN';
        this.exchangeRate = 1650; // Example rate: 1 USD = 1650 NGN (adjust as needed)
        this.initListeners();
    }

    initListeners() {
        const currencyToggle = document.getElementById('currencyToggle');
        if (currencyToggle) {
            currencyToggle.addEventListener('click', () => {
                this.toggleCurrency();
                updatePriceDisplay();
                applyFilters(); // Reapply filters with new currency
            });
        }
    }

    toggleCurrency() {
        this.currentCurrency = this.currentCurrency === 'NGN' ? 'USD' : 'NGN';
        const currencyToggle = document.getElementById('currencyToggle');
        if (currencyToggle) {
            currencyToggle.innerHTML = `<i class="fas fa-money-bill-wave mr-2"></i>${this.currentCurrency}`;
        }
        const priceLabel = document.getElementById('priceLabel');
        if (priceLabel) {
            priceLabel.textContent = `Price Range (${this.currentCurrency})`;
        }
        const priceRangeDisplay = document.getElementById('priceRangeDisplay');
        if (priceRangeDisplay) {
            priceRangeDisplay.textContent = `${this.currentCurrency}0 – No Max`;
        }
        // Clear input fields to avoid confusion with currency switch
        const minPriceInput = document.getElementById('minPrice');
        const maxPriceInput = document.getElementById('maxPrice');
        if (minPriceInput) minPriceInput.value = '';
        if (maxPriceInput) maxPriceInput.value = '';
    }

    convert(price, toCurrency) {
        if (toCurrency === 'USD') {
            return price / this.exchangeRate;
        } else {
            return price * this.exchangeRate;
        }
    }
}

function initMap() {
    map = L.map('map', { zoomControl: false }).setView([6.5244, 3.3792], 12);

    // CartoDB "Voyager" basemap — clean editorial style with subtle colour
    // (green parks, blue water, soft roads); labels are baked in.
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        subdomains: 'abcd',
        maxZoom: 20,
        attribution: '© OpenStreetMap contributors © CARTO'
    }).addTo(map);

    // Zoom is driven by the custom buttons in the chrome (#cwZoomIn / #cwZoomOut).
    const zoomIn = document.getElementById('cwZoomIn');
    const zoomOut = document.getElementById('cwZoomOut');
    if (zoomIn) zoomIn.addEventListener('click', () => map.zoomIn());
    if (zoomOut) zoomOut.addEventListener('click', () => map.zoomOut());
}

async function fetchProperties() {
    try {
        const response = await fetch(URLS.propertiesApi);
        if (!response.ok) throw new Error('Failed to fetch properties');
        properties = await response.json();
        filteredProperties = properties;
        populateYearDropdown();
        updateMap();
        updatePropertyCount();
    } catch (error) {
        console.error('Error fetching properties:', error);
        alert('Error fetching properties. Please try again later.');
    }
}

function populateYearDropdown() {
    const completionYearSelect = document.getElementById('completionYear');
    if (!completionYearSelect) return;

    // Extract unique years from properties' completion_date (format: "Q1 2028")
    const years = new Set();
    properties.forEach(property => {
        if (property.completion_date) {
            const match = property.completion_date.match(/\d{4}/);
            if (match) {
                years.add(parseInt(match[0]));
            }
        }
    });

    // Sort years
    const sortedYears = Array.from(years).sort((a, b) => a - b);

    // Clear existing options (except the first "Year" option)
    completionYearSelect.innerHTML = '<option value="">Year</option>';

    // Add year options
    sortedYears.forEach(year => {
        const option = document.createElement('option');
        option.value = year;
        option.textContent = year;
        completionYearSelect.appendChild(option);
    });
}

function updateMap() {
    map.eachLayer(layer => {
        if (layer instanceof L.Marker || layer instanceof L.MarkerClusterGroup || layer instanceof L.Circle) {
            map.removeLayer(layer);
        }
    });

    const cluster = L.markerClusterGroup({
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true,
        spiderfyOnMaxZoom: true,
        removeOutsideVisibleBounds: true,
        maxClusterRadius: 40,
        // Editorial cluster bubble: ink circle, serif count, sized by child count.
        iconCreateFunction: function (cl) {
            const count = cl.getChildCount();
            const size = Math.round(38 + Math.min(count, 30) * 0.9);
            const fontSize = size > 56 ? 22 : 18;
            return L.divIcon({
                html: `<div class="cw-cluster" style="width:${size}px;height:${size}px;font-size:${fontSize}px;">${count}</div>`,
                className: 'cw-cluster-wrap',
                iconSize: [size, size],
                iconAnchor: [size / 2, size / 2]
            });
        }
    });

    const validMarkers = [];
    filteredProperties.forEach(property => {
        if (!property.latitude || !property.longitude || isNaN(property.latitude) || isNaN(property.longitude)) {
            console.warn(`Invalid coordinates for ${property.name}`);
            return;
        }

        // Create marker icon with location privacy indicator
        const isExact = property.is_exact_location !== false; // Default to true if not specified
        const markerClass = isExact ? 'custom-marker' : 'custom-marker fuzzy-location';

        const icon = L.divIcon({
            html: `<div class="${markerClass}">
                <img src="${property.thumbnail || 'https://via.placeholder.com/40'}" alt="${property.name}"/>
                ${!isExact ? '<span class="fuzzy-indicator" title="Approximate location"><i class="fas fa-question-circle"></i></span>' : ''}
            </div>`,
            className: 'custom-marker-container',
            iconSize: [52, 62],
            iconAnchor: [26, 62]
        });

        const marker = L.marker([property.latitude, property.longitude], { icon });
        marker.on('click', () => showPropertyModal(property));
        cluster.addLayer(marker);
        validMarkers.push(marker);

        // Add fuzzy location circle overlay if not exact
        if (!isExact && property.fuzzy_radius && property.fuzzy_radius > 0) {
            const circle = L.circle([property.latitude, property.longitude], {
                color: '#3b82f6',
                fillColor: '#93c5fd',
                fillOpacity: 0.15,
                weight: 1,
                radius: property.fuzzy_radius,
                dashArray: '5, 5'
            });

            circle.bindTooltip('Approximate location area', {
                permanent: false,
                direction: 'top'
            });

            map.addLayer(circle);
        }
    });

    map.addLayer(cluster);
    if (validMarkers.length > 0) {
        const group = new L.featureGroup(validMarkers);
        map.fitBounds(group.getBounds().pad(0.1));
    }
}

function extractPhoneNumber(contact) {
    if (contact && contact.includes(' - ')) {
        return contact.split(' - ')[1].trim();
    }
    return contact;
}

function formatWhatsAppNumber(phoneNumber) {
    let cleanNumber = phoneNumber.replace(/\D/g, '');
    if (cleanNumber.startsWith('0')) {
        cleanNumber = '234' + cleanNumber.substring(1);
    }
    if (!cleanNumber.startsWith('234')) {
        cleanNumber = '234' + cleanNumber;
    }
    return cleanNumber;
}

function createModalHTML(property) {
    currentImageIndex = 0;

    const images = Array.isArray(property.images) && property.images.length > 0
        ? property.images
        : [property.thumbnail || 'https://via.placeholder.com/200'];

    const formatNaira = (raw) => currencyConverter.currentCurrency === 'USD'
        ? `$${currencyConverter.convert(raw, 'USD').toLocaleString('en-US', { maximumFractionDigits: 0 })}`
        : `₦${raw.toLocaleString()}`;

    // "Starting from" — lowest configuration price, if any.
    const configPrices = (property.configurations || [])
        .map(c => (c.price && c.price !== 'TBD') ? (parseFloat(c.price.replace(/[₦,]/g, '')) || 0) : 0)
        .filter(v => v > 0);
    const minPriceRaw = configPrices.length ? Math.min(...configPrices) : null;
    const priceCardDisplay = minPriceRaw ? formatNaira(minPriceRaw) : 'Price on Request';

    // Status heuristic from completion text.
    const completion = (property.completion_date || '').toString();
    const isReady = /ready|complete/i.test(completion);
    const statusClass = isReady ? 'available' : 'progress';
    const statusLabel = isReady ? 'Available' : 'In Progress';

    // Contact (name before " - ", phone after) + WhatsApp deep link.
    const contactName = (property.contact && property.contact.includes(' - '))
        ? property.contact.split(' - ')[0].trim() : '';
    const phoneNumber = extractPhoneNumber(property.contact);
    const whatsappNumber = formatWhatsAppNumber(phoneNumber);
    // Prefilled enquiry message (config prices arrive as formatted strings, so parse them).
    const waLoc = (property.address || '').split(',')[0] || '';
    const waPrices = (property.configurations || [])
        .map(c => parseFloat(String(c.price).replace(/[^0-9.]/g, '')))
        .filter(n => n > 0);
    const waPrice = waPrices.length ? '₦' + Math.min(...waPrices).toLocaleString('en-NG', { maximumFractionDigits: 0 }) : 'Price on Request';
    const waUrl = `${window.location.origin}/property/${property.id}/`;
    const whatsappMessage = encodeURIComponent(CWCards.enquiryMessage({
        contactName: contactName, propertyName: property.name, location: waLoc, priceStr: waPrice, url: waUrl,
    }));
    const whatsappLink = `https://wa.me/${whatsappNumber}?text=${whatsappMessage}`;

    const configurationsHTML = (property.configurations || []).map(config => {
        let priceDisplay = 'On Request';
        if (config.price && config.price !== 'TBD') {
            priceDisplay = formatNaira(parseFloat(config.price.replace(/[₦,]/g, '')) || 0);
        }
        return `
            <div class="config-row">
                <div>
                    <div style="font-weight:600; font-size:14.5px;">${config.type}</div>
                    <div style="font-size:12.5px; color:var(--slate-500); font-family:var(--font-mono); margin-top:2px;">
                        ${config.bedrooms || 0} bd · ${config.bathrooms || 0} ba · ${(config.square_footage || 0).toLocaleString()} sqft
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-weight:600; font-size:14px; color:var(--coral-700); font-variant-numeric:tabular-nums;">${priceDisplay}</div>
                    <span class="status-v2 available" style="padding:3px 8px; margin-top:4px;"><span class="dot"></span>Available</span>
                </div>
            </div>`;
    }).join('');

    const amenitiesHTML = (property.amenities || []).map(a => `
        <div class="amenity-chip">
            <span class="amenity-icon"><svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z"/></svg></span>
            ${a}
        </div>`).join('');

    const progressHTML = (property.progress_updates || []).map(update => `
        <div class="cw-progress-card ${update.is_latest ? 'latest' : ''}">
            ${update.is_latest ? '<span class="status-v2 new" style="margin-bottom:10px;"><span class="dot"></span>Latest update</span>' : ''}
            <div style="display:flex; justify-content:space-between; align-items:baseline;">
                <div style="font-weight:600; font-size:14px;">${update.stage}</div>
                <div style="font-family:var(--font-mono); font-size:13px; color:var(--coral);">${update.progress_percentage}%</div>
            </div>
            <div class="progress-bar-v2" style="margin-top:10px;"><div class="fill" style="width:${update.progress_percentage}%"></div></div>
            <div style="display:flex; justify-content:space-between; gap:12px; margin-top:10px; font-size:12.5px;">
                <span style="color:var(--slate-600);">${update.description || ''}</span>
                <span style="color:var(--slate-400); font-family:var(--font-mono); white-space:nowrap;">${new Date(update.update_date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}</span>
            </div>
            ${update.uploaded_by ? `<div style="font-size:12px; color:var(--slate-400); margin-top:6px;"><i class="fas fa-user-circle"></i> Updated by ${update.uploaded_by}</div>` : ''}
            ${update.images && update.images.length > 0 ? `
                <div class="cw-progress-imgs">
                    ${update.images.slice(0, 4).map((img, i) => `
                        <div class="cell" onclick="window.open('${img}', '_blank')">
                            <img src="${img}" alt="Progress ${i + 1}" loading="lazy">
                            ${i === 3 && update.images.length > 4 ? `<div class="more-overlay">+${update.images.length - 4}</div>` : ''}
                        </div>`).join('')}
                </div>` : ''}
        </div>`).join('');

    const dotsHTML = images.length > 1 ? `
        <div class="cw-modal-dots">
            ${images.map((_, idx) => `<button type="button" class="gallery-indicator ${idx === currentImageIndex ? 'active' : ''}" onclick="setImage(${idx}, ${property.id})" aria-label="Image ${idx + 1}"></button>`).join('')}
            <span style="margin-left:auto; font-size:12px; font-family:var(--font-mono); color:rgba(255,255,255,0.85);">${images.length} photos</span>
        </div>` : '';

    const arrowsHTML = images.length > 1 ? `
        <button class="cw-modal-arrow left" onclick="changeImage(-1, ${property.id})" aria-label="Previous image"><i class="fas fa-chevron-left"></i></button>
        <button class="cw-modal-arrow right" onclick="changeImage(1, ${property.id})" aria-label="Next image"><i class="fas fa-chevron-right"></i></button>` : '';

    return `
        <div class="detail-modal">
            <button onclick="closeModal()" class="cw-modal-close" aria-label="Close">&times;</button>

            <!-- LEFT · visuals -->
            <div class="detail-left">
                <img src="${images[currentImageIndex]}" alt="${property.name}" id="galleryImage"
                     style="position:absolute; inset:0; width:100%; height:100%; object-fit:cover;">
                <div class="img-gradient"></div>

                <div style="position:absolute; top:18px; left:18px; right:18px; display:flex; justify-content:space-between; align-items:flex-start; gap:8px; z-index:2;">
                    <div style="display:flex; flex-wrap:wrap; gap:8px;">
                        <span class="status-v2 ${statusClass}" style="background:rgba(255,255,255,0.92);"><span class="dot"></span>${statusLabel}</span>
                        ${property.luxury_status ? `<span class="status-v2 new" style="background:rgba(255,255,255,0.92);"><span class="dot"></span>${property.luxury_status}</span>` : ''}
                        ${!property.is_exact_location ? '<span class="status-v2 sold" style="background:rgba(255,255,255,0.92);"><span class="dot"></span>Approx</span>' : ''}
                    </div>
                    ${window.isInternalUser ? `
                        <label class="cw-compare-chip">
                            <input type="checkbox" class="dashboard-property-checkbox" value="${property.id}"
                                   ${selectedPropertyIds.has(property.id.toString()) ? 'checked' : ''}
                                   onchange="togglePropertySelection(this)" style="accent-color:var(--coral);">
                            Compare
                        </label>` : ''}
                </div>

                ${arrowsHTML}

                <div class="identity">
                    <div style="display:flex; align-items:center; gap:8px; opacity:0.92;">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="white" stroke="none"><path d="M12 22s7-6.13 7-12a7 7 0 1 0-14 0c0 5.87 7 12 7 12z"/><circle cx="12" cy="10" r="2.5" fill="var(--coral)"/></svg>
                        <span class="eyebrow" style="color:white; font-size:10px;">${property.address}</span>
                    </div>
                    <h1 class="serif-display" style="font-size:clamp(28px, 4.5vw, 46px); margin:6px 0 12px; letter-spacing:-0.02em;">${property.name}</h1>
                    ${(contactName || phoneNumber) ? `
                        <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
                            ${contactName ? `
                                <div style="display:flex; align-items:center; gap:10px;">
                                    <div style="width:40px; height:40px; border-radius:50%; background:linear-gradient(135deg, var(--navy), var(--navy-700)); display:flex; align-items:center; justify-content:center; font-weight:600; color:white; font-size:13px;">${contactName.charAt(0).toUpperCase()}</div>
                                    <div>
                                        <div style="font-size:12px; opacity:0.7;">Lead by</div>
                                        <div style="font-size:14px; font-weight:500;">${contactName}</div>
                                    </div>
                                </div>` : ''}
                            ${phoneNumber ? `<a href="${whatsappLink}" target="_blank" rel="noopener" class="btn-v2" style="margin-left:auto; background:rgba(255,255,255,0.15); color:white; border:1px solid rgba(255,255,255,0.3); padding:8px 14px; backdrop-filter:blur(8px); font-size:13px;"><i class="fab fa-whatsapp"></i> ${phoneNumber}</a>` : ''}
                        </div>` : ''}
                    ${dotsHTML}
                </div>
            </div>

            <!-- RIGHT · info -->
            <div class="detail-right">
                <div style="display:flex; flex-direction:column; gap:20px;">

                    <!-- Price card -->
                    <div class="price-card-v2">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap;">
                            <div>
                                <div class="eyebrow">Starting from</div>
                                <p class="serif-display" style="font-size:clamp(28px, 5vw, 40px); line-height:1.05; margin:6px 0 2px;">${priceCardDisplay}</p>
                                ${completion ? `<p style="font-size:13px; color:var(--slate-500);">Completion <span style="font-family:var(--font-mono); color:var(--ink);">${completion}</span></p>` : ''}
                            </div>
                            <span class="status-v2 ${statusClass}" style="padding:4px 10px;"><span class="dot"></span>${statusLabel}</span>
                        </div>
                        <div style="display:flex; gap:8px; margin-top:16px; flex-wrap:wrap;">
                            <button onclick="toggleDashboardEnquiry()" id="dashEnquireBtn" class="btn-v2 btn-coral" style="flex:1; justify-content:center; min-width:150px;"><i class="fas fa-envelope"></i> Enquire Now</button>
                            ${property.brochure ? `<button onclick="downloadBrochure('${property.brochure}')" class="btn-v2 btn-ghost" style="justify-content:center;"><i class="fas fa-file-pdf"></i> Brochure</button>` : ''}
                        </div>
                    </div>

                    ${!property.is_exact_location ? `
                    <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; background:var(--coral-50); border:1px solid var(--coral-100); border-radius:var(--r-md); padding:12px 14px;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <i class="fas fa-shield-alt" style="color:var(--coral); font-size:16px;"></i>
                            <div>
                                <div style="font-weight:600; font-size:13px; color:var(--ink);">Location privacy active</div>
                                <div style="font-size:12px; color:var(--slate-500);">Exact address provided on enquiry</div>
                            </div>
                        </div>
                        <button onclick="requestLocationUnlock(${property.id})" id="unlockBtn${property.id}" class="btn-v2 btn-coral" style="font-size:12.5px; padding:8px 14px; white-space:nowrap;"><i class="fas fa-unlock-alt"></i> Unlock</button>
                    </div>` : ''}

                    ${property.description ? `
                    <div>
                        <div class="eyebrow" style="margin-bottom:10px;">About this property</div>
                        <p style="font-size:14px; line-height:1.65; color:var(--slate-600); margin:0;">${property.description}</p>
                    </div>` : ''}

                    ${(property.configurations || []).length > 0 ? `
                    <div>
                        <div class="eyebrow" style="margin-bottom:12px;">Available Units</div>
                        <div style="display:flex; flex-direction:column; gap:8px;">${configurationsHTML}</div>
                    </div>` : ''}

                    ${(property.amenities || []).length > 0 ? `
                    <div>
                        <div class="eyebrow" style="margin-bottom:12px;">Amenities</div>
                        <div style="display:grid; grid-template-columns:repeat(2, 1fr); gap:8px;">${amenitiesHTML}</div>
                    </div>` : ''}

                    ${(property.progress_updates || []).length > 0 ? `
                    <div>
                        <div class="eyebrow" style="margin-bottom:12px;">Construction Progress</div>
                        ${progressHTML}
                    </div>` : ''}

                    <!-- Enquiry Form Panel -->
                    <div id="dashEnquiryPanel" style="display:none;">
                        <div id="dashEnquirySuccess" style="display:none; padding:18px; background:#E7F6EF; border-radius:var(--r-md); text-align:center; color:#16774E;">
                            <i class="fas fa-check-circle" style="font-size:1.5rem; margin-bottom:8px; display:block;"></i>
                            <strong>Thank you!</strong> We've received your enquiry and will be in touch shortly.
                        </div>
                        <div id="dashEnquiryForm" class="price-card-v2" style="background:#fff; border:1px solid var(--slate-200);">
                            <div class="eyebrow" style="margin-bottom:4px;">Register your interest</div>
                            <p style="font-size:12px; color:var(--slate-400); margin-bottom:14px;">An agent will contact you within 2 business hours.</p>
                            <input type="text" name="website" id="dashHoneypot" style="display:none;" autocomplete="off" tabindex="-1">
                            <div id="dashEnquiryError" style="display:none; padding:10px; background:#fef2f2; border-radius:var(--r-sm); color:#991b1b; font-size:13px; margin-bottom:10px;"></div>
                            <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:10px;">
                                <div>
                                    <label class="dash-label">First name *</label>
                                    <input type="text" id="dashFirstName" class="dash-input" placeholder="Jane">
                                    <div id="dashFirstNameErr" class="dash-field-err" style="display:none;"></div>
                                </div>
                                <div>
                                    <label class="dash-label">Last name *</label>
                                    <input type="text" id="dashLastName" class="dash-input" placeholder="Doe">
                                    <div id="dashLastNameErr" class="dash-field-err" style="display:none;"></div>
                                </div>
                            </div>
                            <div style="margin-bottom:10px;">
                                <label class="dash-label">Email *</label>
                                <input type="email" id="dashEmail" class="dash-input" placeholder="jane@example.com">
                                <div id="dashEmailErr" class="dash-field-err" style="display:none;"></div>
                            </div>
                            <div style="margin-bottom:10px;">
                                <label class="dash-label">Phone</label>
                                <input type="tel" id="dashPhone" class="dash-input" placeholder="+234 800 000 0000">
                                <div id="dashPhoneErr" class="dash-field-err" style="display:none;"></div>
                            </div>
                            <div style="margin-bottom:10px;">
                                <label class="dash-label">Message *</label>
                                <textarea id="dashMessage" rows="3" class="dash-input" style="resize:vertical;" placeholder="I'm interested in this property..."></textarea>
                                <div id="dashMessageErr" class="dash-field-err" style="display:none;"></div>
                            </div>
                            <div style="margin-bottom:10px; display:flex; align-items:flex-start; gap:8px;">
                                <input type="checkbox" id="dashConsent" style="margin-top:3px; flex-shrink:0; accent-color:var(--coral);">
                                <label for="dashConsent" style="font-size:12px; color:var(--slate-500); cursor:pointer;">I agree to be contacted about this property and consent to my data being processed. *</label>
                            </div>
                            <div id="dashConsentErr" class="dash-field-err" style="display:none; margin-bottom:8px;"></div>
                            <button onclick="submitDashboardEnquiry(${property.id})" id="dashSubmitBtn" class="dash-submit">Send Enquiry</button>
                        </div>
                    </div>

                </div>
            </div>
        </div>
    `;
}

function showPropertyModal(property) {
    console.log('Showing modal for property:', property.id);
    currentImageIndex = 0;
    const modalContent = document.getElementById('modalContent');
    if (modalContent) {
        modalContent.parentElement.dataset.propertyId = property.id;
        modalContent.innerHTML = createModalHTML(property);
    }
    const modal = document.getElementById('propertyModal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

function closeModal() {
    console.log('Closing modal');
    const modal = document.getElementById('propertyModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    } else {
        console.error('Modal element not found');
    }
}

function toggleDashboardEnquiry() {
    const panel = document.getElementById('dashEnquiryPanel');
    const btn = document.getElementById('dashEnquireBtn');
    if (!panel) return;
    const visible = panel.style.display !== 'none';
    panel.style.display = visible ? 'none' : 'block';
    if (btn) btn.innerHTML = visible
        ? '<i class="fas fa-envelope"></i> Enquire Now'
        : '<i class="fas fa-times"></i> Close Form';
    if (!visible) {
        // Just opened: the form sits at the bottom of the scrollable info column,
        // so bring it into view and focus the first field.
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        const firstField = document.getElementById('dashFirstName');
        if (firstField) setTimeout(() => firstField.focus(), 350);
    }
}

function submitDashboardEnquiry(propertyId) {
    // Clear previous errors
    ['dashFirstNameErr','dashLastNameErr','dashEmailErr','dashPhoneErr','dashMessageErr','dashConsentErr','dashEnquiryError'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.style.display = 'none'; el.textContent = ''; }
    });

    const honeypot = document.getElementById('dashHoneypot');
    if (honeypot && honeypot.value) return; // bot trap

    const firstName = (document.getElementById('dashFirstName') || {}).value || '';
    const lastName  = (document.getElementById('dashLastName')  || {}).value || '';
    const email     = (document.getElementById('dashEmail')     || {}).value || '';
    const phone     = (document.getElementById('dashPhone')     || {}).value || '';
    const message   = (document.getElementById('dashMessage')   || {}).value || '';
    const consent   = document.getElementById('dashConsent') && document.getElementById('dashConsent').checked;

    const body = new URLSearchParams({
        first_name: firstName,
        last_name:  lastName,
        email:      email,
        phone:      phone,
        message:    message,
        consent:    consent ? 'on' : '',
    });

    // Read CSRF token from cookie
    const csrfToken = (document.cookie.split(';').find(c => c.trim().startsWith('csrftoken=')) || '').split('=')[1] || '';

    const submitBtn = document.getElementById('dashSubmitBtn');
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Sending…'; }

    fetch(`/crm/enquire/${propertyId}/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': csrfToken,
        },
        body: body.toString(),
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            const formDiv = document.getElementById('dashEnquiryForm');
            const successDiv = document.getElementById('dashEnquirySuccess');
            if (formDiv) formDiv.style.display = 'none';
            if (successDiv) successDiv.style.display = 'block';
            const btn = document.getElementById('dashEnquireBtn');
            if (btn) btn.style.display = 'none';
        } else if (data.errors) {
            const fieldMap = {
                first_name: 'dashFirstNameErr',
                last_name:  'dashLastNameErr',
                email:      'dashEmailErr',
                phone:      'dashPhoneErr',
                message:    'dashMessageErr',
                consent:    'dashConsentErr',
            };
            Object.entries(data.errors).forEach(([field, msgs]) => {
                const errId = fieldMap[field];
                if (errId) {
                    const el = document.getElementById(errId);
                    if (el) { el.textContent = msgs[0]; el.style.display = 'block'; }
                } else {
                    const gen = document.getElementById('dashEnquiryError');
                    if (gen) { gen.textContent = msgs[0]; gen.style.display = 'block'; }
                }
            });
            if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Send Enquiry'; }
        }
    })
    .catch(() => {
        const gen = document.getElementById('dashEnquiryError');
        if (gen) { gen.textContent = 'Something went wrong. Please try again.'; gen.style.display = 'block'; }
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Send Enquiry'; }
    });
}

function changeImage(delta, propertyId) {
    console.log('Changing image:', { delta, propertyId, currentImageIndex });
    const property = filteredProperties.find(p => p.id === parseInt(propertyId));
    if (!property) {
        console.error('Property not found:', propertyId);
        return;
    }
    const images = Array.isArray(property.images) && property.images.length > 0 
        ? property.images 
        : [property.thumbnail || 'https://via.placeholder.com/200'];
    currentImageIndex = (currentImageIndex + delta + images.length) % images.length;
    const galleryImage = document.getElementById('galleryImage');
    if (galleryImage) {
        galleryImage.style.opacity = '0.7';
        setTimeout(() => {
            galleryImage.src = images[currentImageIndex];
            galleryImage.style.opacity = '1';
            updateGalleryIndicators();
        }, 200);
    } else {
        console.error('Gallery image element not found');
    }
}

function setImage(index, propertyId) {
    console.log('Setting image:', { index, propertyId });
    const property = filteredProperties.find(p => p.id === parseInt(propertyId));
    if (!property) {
        console.error('Property not found:', propertyId);
        return;
    }
    const images = Array.isArray(property.images) && property.images.length > 0 
        ? property.images 
        : [property.thumbnail || 'https://via.placeholder.com/200'];
    currentImageIndex = Math.max(0, Math.min(index, images.length - 1));
    const galleryImage = document.getElementById('galleryImage');
    if (galleryImage) {
        galleryImage.style.opacity = '0.7';
        setTimeout(() => {
            galleryImage.src = images[currentImageIndex];
            galleryImage.style.opacity = '1';
            updateGalleryIndicators();
        }, 200);
    } else {
        console.error('Gallery image element not found');
    }
}

function updateGalleryIndicators() {
    const indicators = document.querySelectorAll('.gallery-indicator');
    indicators.forEach((indicator, idx) => {
        indicator.classList.toggle('active', idx === currentImageIndex);
    });
}


function downloadBrochure(url) {
    if (url) {
        window.location.href = url;
    } else {
        alert('No brochure available for this property.');
    }
}

function handleSearch() {
    const searchInput = document.getElementById('searchInput');
    const searchInputSidebar = document.getElementById('searchInputSidebar');
    const term = (searchInput ? searchInput.value : '') || (searchInputSidebar ? searchInputSidebar.value : '');
    filteredProperties = properties.filter(p => 
        p.name.toLowerCase().includes(term.toLowerCase()) || 
        p.address.toLowerCase().includes(term.toLowerCase())
    );
    updateMap();
    updatePropertyCount();
}

function updatePropertyCount() {
    const propertyCount = document.getElementById('propertyCount');
    if (propertyCount) {
        propertyCount.innerHTML = `<i class="fas fa-chart-bar mr-2"></i>${filteredProperties.length} Properties`;
    }
}

function resetMap() {
    map.setView([6.5244, 3.3792], 12);
}

function refreshData() {
    fetchProperties();
}

function toggleFilters() {
    const sidebar = document.getElementById('filterSidebar');
    const overlay = document.getElementById('mobileFilterOverlay');
    if (sidebar) {
        const isOpen = sidebar.classList.contains('open');
        sidebar.classList.toggle('open');
        if (overlay) {
            overlay.classList.toggle('active', !isOpen);
        }
        document.body.style.overflow = isOpen ? '' : 'hidden';
    }
}

function updateRangeDisplay(type) {
    const minField = document.getElementById(`min${type}`);
    const maxField = document.getElementById(`max${type}`);
    const display = document.getElementById(`${type.toLowerCase()}RangeDisplay`);
    
    const minVal = parseInt(minField ? minField.value : 0) || null;
    const maxVal = parseInt(maxField ? maxField.value : 0) || null;
    
    let displayText = `Any number of ${type.toLowerCase()}`;
    
    if (minVal && maxVal) {
        displayText = `${minVal} - ${maxVal} ${type.toLowerCase()}`;
    } else if (minVal) {
        displayText = `${minVal}+ ${type.toLowerCase()}`;
    } else if (maxVal) {
        displayText = `Up to ${maxVal} ${type.toLowerCase()}`;
    }
    
    if (display) {
        display.textContent = displayText;
    }
}

function updateLuxuryStatusDisplay() {
    const luxuryStatus = document.getElementById('luxuryStatus');
    const display = document.getElementById('luxuryStatusDisplay');
    if (luxuryStatus && display) {
        display.textContent = luxuryStatus.value === 'all' ? 'Any status' : luxuryStatus.value;
    }
}

function updatePriceDisplay() {
    const minPrice = parseFloat(document.getElementById('minPrice') ? document.getElementById('minPrice').value : 0) || 0;
    const maxPrice = parseFloat(document.getElementById('maxPrice') ? document.getElementById('maxPrice').value : 0) || Infinity;
    const display = document.getElementById('priceRangeDisplay');
    if (display) {
        const convertedMin = currencyConverter.currentCurrency === 'USD' 
            ? currencyConverter.convert(minPrice, 'USD') 
            : minPrice;
        const convertedMax = currencyConverter.currentCurrency === 'USD' 
            ? currencyConverter.convert(maxPrice, 'USD') 
            : maxPrice;
        display.textContent = `${currencyConverter.currentCurrency}${convertedMin.toLocaleString('en-US', { maximumFractionDigits: 0 })} – ${maxPrice === Infinity ? 'No Max' : currencyConverter.currentCurrency + convertedMax.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
    }
}

function applyFilters() {
    const minPriceInput = parseFloat(document.getElementById('minPrice') ? document.getElementById('minPrice').value : 0) || 0;
    const maxPriceInput = parseFloat(document.getElementById('maxPrice') ? document.getElementById('maxPrice').value : 0) || Infinity;
    const minBedrooms = parseInt(document.getElementById('minBedrooms') ? document.getElementById('minBedrooms').value : 0) || null;
    const maxBedrooms = parseInt(document.getElementById('maxBedrooms') ? document.getElementById('maxBedrooms').value : 0) || null;
    const minBathrooms = parseInt(document.getElementById('minBathrooms') ? document.getElementById('minBathrooms').value : 0) || null;
    const maxBathrooms = parseInt(document.getElementById('maxBathrooms') ? document.getElementById('maxBathrooms').value : 0) || null;
    const luxuryStatus = document.getElementById('luxuryStatus') ? document.getElementById('luxuryStatus').value : 'all';

    // ✅ Get selected completion quarter and year
    const completionQuarter = document.getElementById('completionQuarter') ? document.getElementById('completionQuarter').value : '';
    const completionYear = document.getElementById('completionYear') ? document.getElementById('completionYear').value : '';

    // Convert quarter and year to date range
    let completionStartDate = null;
    let completionEndDate = null;

    if (completionQuarter && completionYear) {
        const year = parseInt(completionYear);
        const quarter = parseInt(completionQuarter);

        const quarterDates = {
            1: { startMonth: 0, startDay: 1, endMonth: 2, endDay: 31 },    // Q1: Jan 1 - Mar 31
            2: { startMonth: 3, startDay: 1, endMonth: 5, endDay: 30 },    // Q2: Apr 1 - Jun 30
            3: { startMonth: 6, startDay: 1, endMonth: 8, endDay: 30 },    // Q3: Jul 1 - Sep 30
            4: { startMonth: 9, startDay: 1, endMonth: 11, endDay: 31 }    // Q4: Oct 1 - Dec 31
        };

        if (quarterDates[quarter]) {
            const q = quarterDates[quarter];
            completionStartDate = new Date(year, q.startMonth, q.startDay);
            completionEndDate = new Date(year, q.endMonth, q.endDay);
            completionStartDate.setHours(0, 0, 0, 0);
            completionEndDate.setHours(23, 59, 59, 999);
        }
    }

    // Convert input prices to NGN (base currency) for filtering
    const minPriceNGN = currencyConverter.currentCurrency === 'USD'
        ? currencyConverter.convert(minPriceInput, 'NGN')
        : minPriceInput;
    const maxPriceNGN = currencyConverter.currentCurrency === 'USD'
        ? currencyConverter.convert(maxPriceInput, 'NGN')
        : maxPriceInput;

    filteredProperties = properties.filter(p => {
        // ✅ Completion period check (quarter and year)
        let matchesCompletionDate = true;
        if (completionQuarter && completionYear) {
            const expectedQuarterString = `Q${completionQuarter} ${completionYear}`;
            matchesCompletionDate = p.completion_date === expectedQuarterString;
        }
        let matchesLuxury = true;
        if (luxuryStatus !== 'all') {
            matchesLuxury = p.luxury_status && p.luxury_status.toLowerCase() === luxuryStatus.toLowerCase();
        }

        const matchesConfig = p.configurations.some(c => {
        const price = c.price === 'TBD' ? Infinity : parseFloat(c.price.replace(/[₦,]/g, '')) || 0;
        const matchesPrice = price >= minPriceNGN && price <= maxPriceNGN;

        let matchesBedrooms = true;
        if (minBedrooms !== null) matchesBedrooms = c.bedrooms >= minBedrooms;
        if (maxBedrooms !== null) matchesBedrooms = matchesBedrooms && c.bedrooms <= maxBedrooms;

        let matchesBathrooms = true;
        if (minBathrooms !== null) matchesBathrooms = c.bathrooms >= minBathrooms;
        if (maxBathrooms !== null) matchesBathrooms = matchesBathrooms && c.bathrooms <= maxBathrooms;

        return matchesPrice && matchesBedrooms && matchesBathrooms;
    });

    return matchesCompletionDate && matchesLuxury && matchesConfig;
});
    updateMap();
    updatePropertyCount();
    
    updatePriceDisplay();
    updateRangeDisplay('Bedrooms');
    updateRangeDisplay('Bathrooms');
    updateLuxuryStatusDisplay();
    toggleFilters();
}

function clearFilters() {
    const minPriceInput = document.getElementById('minPrice');
    const maxPriceInput = document.getElementById('maxPrice');
    const minBedroomsInput = document.getElementById('minBedrooms');
    const maxBedroomsInput = document.getElementById('maxBedrooms');
    const minBathroomsInput = document.getElementById('minBathrooms');
    const maxBathroomsInput = document.getElementById('maxBathrooms');
    const luxuryStatusInput = document.getElementById('luxuryStatus');
    const searchInputSidebar = document.getElementById('searchInputSidebar');
    const completionQuarterEl = document.getElementById('completionQuarter');
    const completionYearEl = document.getElementById('completionYear');

    if (minPriceInput) minPriceInput.value = '';
    if (maxPriceInput) maxPriceInput.value = '';
    if (minBedroomsInput) minBedroomsInput.value = '';
    if (maxBedroomsInput) maxBedroomsInput.value = '';
    if (minBathroomsInput) minBathroomsInput.value = '';
    if (maxBathroomsInput) maxBathroomsInput.value = '';
    if (luxuryStatusInput) luxuryStatusInput.value = 'all';
    if (searchInputSidebar) searchInputSidebar.value = '';
    if (completionQuarterEl) completionQuarterEl.value = '';
    if (completionYearEl) completionYearEl.value = '';
    
    filteredProperties = properties;
    updateMap();
    updatePropertyCount();
    
    const priceRangeDisplay = document.getElementById('priceRangeDisplay');
    const bedroomsRangeDisplay = document.getElementById('bedroomsRangeDisplay');
    const bathroomsRangeDisplay = document.getElementById('bathroomsRangeDisplay');
    const luxuryStatusDisplay = document.getElementById('luxuryStatusDisplay');
    
    if (priceRangeDisplay) priceRangeDisplay.textContent = `${currencyConverter.currentCurrency}0 – No Max`;
    if (bedroomsRangeDisplay) bedroomsRangeDisplay.textContent = 'Any number of bedrooms';
    if (bathroomsRangeDisplay) bathroomsRangeDisplay.textContent = 'Any number of bathrooms';
    if (luxuryStatusDisplay) luxuryStatusDisplay.textContent = 'Any status';
    toggleFilters();
}

// Draggable Search Box
let isDragging = false;
let dragOffset = { x: 0, y: 0 };
const searchBox = document.getElementById('searchBox');

function handleDragStart(e) {
    if (e.target.closest('input')) return;
    e.preventDefault();
    isDragging = true;
    const clientX = e.clientX || (e.touches && e.touches[0].clientX);
    const clientY = e.clientY || (e.touches && e.touches[0].clientY);
    dragOffset = {
        x: clientX - parseInt(searchBox.style.left || 0),
        y: clientY - parseInt(searchBox.style.top || 0)
    };
}

function handleDragMove(e) {
    if (!isDragging) return;
    const clientX = e.clientX || (e.touches && e.touches[0].clientX);
    const clientY = e.clientY || (e.touches && e.touches[0].clientY);
    searchBox.style.left = Math.max(0, Math.min(window.innerWidth - 320, clientX - dragOffset.x)) + 'px';
    searchBox.style.top = Math.max(0, Math.min(window.innerHeight - 50, clientY - dragOffset.y)) + 'px';
}

function handleDragEnd() {
    isDragging = false;
}

if (searchBox) {
    searchBox.addEventListener('mousedown', handleDragStart);
    searchBox.addEventListener('touchstart', handleDragStart);
}
document.addEventListener('mousemove', handleDragMove);
document.addEventListener('touchmove', handleDragMove, { passive: false });
document.addEventListener('mouseup', handleDragEnd);
document.addEventListener('touchend', handleDragEnd);

// Event Listeners Setup
document.addEventListener('DOMContentLoaded', function() {
    initMap();
    currencyConverter = new CurrencyConverter();
    fetchProperties();

    // Initialize compare button
    updateDashboardCompareButton();

    const searchInput = document.getElementById('searchInput');
    const searchInputSidebar = document.getElementById('searchInputSidebar');
    const luxuryStatus = document.getElementById('luxuryStatus');
    const minBedrooms = document.getElementById('minBedrooms');
    const maxBedrooms = document.getElementById('maxBedrooms');
    const minBathrooms = document.getElementById('minBathrooms');
    const maxBathrooms = document.getElementById('maxBathrooms');
    const minPrice = document.getElementById('minPrice');
    const maxPrice = document.getElementById('maxPrice');
    const completionQuarter = document.getElementById('completionQuarter');
    const completionYear = document.getElementById('completionYear');

    if (searchInput) searchInput.addEventListener('input', handleSearch);
    if (searchInputSidebar) searchInputSidebar.addEventListener('input', handleSearch);
    if (luxuryStatus) luxuryStatus.addEventListener('change', updateLuxuryStatusDisplay);
    if (minBedrooms) minBedrooms.addEventListener('input', () => updateRangeDisplay('Bedrooms'));
    if (maxBedrooms) maxBedrooms.addEventListener('input', () => updateRangeDisplay('Bedrooms'));
    if (minBathrooms) minBathrooms.addEventListener('input', () => updateRangeDisplay('Bathrooms'));
    if (maxBathrooms) maxBathrooms.addEventListener('input', () => updateRangeDisplay('Bathrooms'));
    if (minPrice) minPrice.addEventListener('input', updatePriceDisplay);
    if (maxPrice) maxPrice.addEventListener('input', updatePriceDisplay);

    // Update completion period display
    const updateCompletionDisplay = () => {
        const completionDateDisplay = document.getElementById('completionDateDisplay');
        if (completionDateDisplay && completionQuarter && completionYear) {
            if (completionQuarter.value && completionYear.value) {
                completionDateDisplay.textContent = `Q${completionQuarter.value} ${completionYear.value}`;
            } else {
                completionDateDisplay.textContent = 'Any period';
            }
        }
    };

    if (completionQuarter) completionQuarter.addEventListener('change', updateCompletionDisplay);
    if (completionYear) completionYear.addEventListener('change', updateCompletionDisplay);
    
    if (searchBox) {
        searchBox.style.left = (window.innerWidth / 2 - (window.innerWidth < 768 ? window.innerWidth / 2 - 10 : 150)) + 'px';
        searchBox.style.top = '10px';
    }

    const modal = document.getElementById('propertyModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                closeModal();
            }
        });
    }
    
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeModal();
        }
    });
});

// Location unlock functionality
async function requestLocationUnlock(propertyId) {
    const button = document.getElementById(`unlockBtn${propertyId}`);
    if (!button) return;

    const originalText = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>Requesting...';

    try {
        const response = await fetch(`/api/property/${propertyId}/request-unlock/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();

        if (response.ok && data.success) {
            button.innerHTML = '<i class="fas fa-check mr-1"></i>Location Unlocked!';
            button.classList.remove('bg-blue-500', 'hover:bg-blue-600');
            button.classList.add('bg-green-500');

            // Show success message
            showNotification('Success! Reloading property data...', 'success');

            // Reload properties to get exact location
            setTimeout(async () => {
                await fetchProperties();
                closeModal();
                showNotification('Property locations updated. Click the property again to see exact location.', 'info');
            }, 1500);

        } else {
            throw new Error(data.error || 'Failed to unlock location');
        }

    } catch (error) {
        console.error('Error unlocking location:', error);
        showNotification(error.message || 'Failed to unlock location. Please try again.', 'error');
        button.disabled = false;
        button.innerHTML = originalText;
    }
}

// Get CSRF token from cookies
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Show notification toast
function showNotification(message, type = 'info') {
    // Check if notification container exists, create if not
    let container = document.getElementById('notificationContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notificationContainer';
        container.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 10000;';
        document.body.appendChild(container);
    }

    const notification = document.createElement('div');
    const bgColors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        info: 'bg-blue-500',
        warning: 'bg-yellow-500'
    };

    notification.className = `${bgColors[type] || bgColors.info} text-white px-6 py-3 rounded-lg shadow-lg mb-2 transition-opacity duration-300`;
    notification.innerHTML = `
        <div class="flex items-center gap-2">
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
            <span>${message}</span>
        </div>
    `;

    container.appendChild(notification);

    // Auto remove after 4 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 4000);
}

// Dashboard Property Comparison Functionality
function togglePropertySelection(checkbox) {
    const propertyId = checkbox.value;

    if (checkbox.checked) {
        selectedPropertyIds.add(propertyId);
    } else {
        selectedPropertyIds.delete(propertyId);
    }

    updateDashboardCompareButton();
}

function updateDashboardCompareButton() {
    const count = selectedPropertyIds.size;

    const countSpan = document.getElementById('dashboardSelectedCount');
    if (countSpan) {
        countSpan.textContent = count;
    }

    const compareBtn = document.getElementById('dashboardCompareBtn');
    if (compareBtn) {
        compareBtn.disabled = count < 2;
        if (count >= 2) {
            compareBtn.title = `Compare ${count} properties`;
        } else {
            compareBtn.title = 'Select 2+ properties to compare';
        }
    }
}

// Compare Selected Properties
async function compareDashboardProperties() {
    const selectedProperties = Array.from(selectedPropertyIds);

    if (selectedProperties.length < 2) {
        showNotification('Please select at least 2 properties to compare', 'warning');
        return;
    }

    const modal = document.getElementById('comparisonModal');
    const content = document.getElementById('comparisonContent');

    content.innerHTML = `
        <div class="flex items-center justify-center py-12">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            <span class="ml-3 text-gray-600">Loading comparison...</span>
        </div>
    `;

    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    try {
        const response = await fetch(URLS.compareProperties, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN
            },
            body: JSON.stringify({ property_ids: selectedProperties })
        });

        if (!response.ok) throw new Error('Failed to fetch comparison data');

        const data = await response.json();
        if (!data.success) throw new Error(data.error);

        content.innerHTML = buildComparisonTable(data.properties);

        const pdfLink = document.getElementById('downloadComparisonPdf');
        if (pdfLink) {
            pdfLink.href = data.comparison_url;
        }
    } catch (error) {
        console.error('Error fetching comparison:', error);
        content.innerHTML = `
            <div class="text-center py-12">
                <div class="bg-red-50 border border-red-200 rounded-lg p-6">
                    <i class="fas fa-exclamation-triangle text-red-500 text-4xl mb-4"></i>
                    <h3 class="text-lg font-semibold text-red-800 mb-2">Error Loading Comparison</h3>
                    <p class="text-red-600 mb-4">We couldn't load the comparison. Please try again.</p>
                </div>
            </div>
        `;
    }
}

function buildComparisonTable(properties) {
    let html = '<div class="overflow-x-auto"><table class="min-w-full border-collapse">';
    // Headers
    html += '<thead><tr class="bg-gray-100">';
    html += '<th class="p-4 border text-left font-bold text-gray-800">Feature</th>';
    properties.forEach(prop => {
        html += `<th class="p-4 border text-center font-bold text-gray-800">${prop.name}</th>`;
    });
    html += '</tr></thead><tbody>';

    // Features
    const features = [
        { key: 'address', label: 'Address', format: v => v || 'N/A' },
        { key: 'luxury_status', label: 'Luxury Status', format: v => v === 'luxurious' ? '<span class="text-amber-600 font-semibold"><i class="fas fa-crown mr-1"></i>Luxurious</span>' : 'Non-Luxurious' },
        { key: 'min_price', label: 'Min Price', format: v => {
            if (!v) return 'On Request';
            if (currencyConverter.currentCurrency === 'USD') {
                const usd = v / currencyConverter.exchangeRate;
                return `$${usd < 1000 ? usd.toLocaleString('en-US', {maximumFractionDigits: 0}) : (usd/1000).toFixed(1) + 'K'}`;
            } else {
                return `₦${v.toLocaleString()}`;
            }
        }},
        { key: 'description', label: 'Description', format: v => v || 'N/A' },
        { key: 'contact_phone', label: 'Contact Phone', format: v => v || 'N/A' },
        { key: 'amenities', label: 'Amenities', format: v => v.length > 0 ? v.join(', ') : 'None' },
        { key: 'configurations', label: 'Configurations', format: v => v.map(c => {
            let price = c.price;
            if (price) {
                if (currencyConverter.currentCurrency === 'USD') {
                    price = price / currencyConverter.exchangeRate;
                    price = `$${price < 1000 ? price.toLocaleString('en-US', {maximumFractionDigits: 0}) : (price/1000).toFixed(1) + 'K'}`;
                } else {
                    price = `₦${price.toLocaleString()}`;
                }
            } else {
                price = 'TBD';
            }
            return `${c.bedrooms} Bed, ${c.bathrooms} Bath - ${price}`;
        }).join('<br>') || 'N/A' }
    ];

    features.forEach(feature => {
        html += `<tr class="hover:bg-gray-50"><td class="p-4 border font-semibold text-gray-700">${feature.label}</td>`;
        properties.forEach(prop => {
            let value = prop[feature.key];
            value = feature.format(value);
            html += `<td class="p-4 border text-gray-600">${value}</td>`;
        });
        html += '</tr>';
    });

    html += '</tbody></table></div>';
    return html;
}

function closeDashboardComparisonModal() {
    const modal = document.getElementById('comparisonModal');
    modal.style.display = 'none';
    document.body.style.overflow = '';
}

// Event listener for compare button
const dashboardCompareBtn = document.getElementById('dashboardCompareBtn');
if (dashboardCompareBtn) {
    dashboardCompareBtn.addEventListener('click', compareDashboardProperties);
}

// Click outside modal to close
const comparisonModal = document.getElementById('comparisonModal');
if (comparisonModal) {
    comparisonModal.addEventListener('click', function(e) {
        if (e.target === this) {
            closeDashboardComparisonModal();
        }
    });
}

// Escape key to close
document.addEventListener('keydown', function(e) {
    const modal = document.getElementById('comparisonModal');
    if (modal && modal.style.display !== 'none' && e.key === 'Escape') {
        closeDashboardComparisonModal();
    }
});

// ============================================
// Chat Widget Functionality
// ============================================

// Initialize chat widget configuration (URL set from template)
window.ChatWidgetConfig = window.ChatWidgetConfig || {
    webhook: {
        url: '',
        route: 'general'
    },
    style: {
        primaryColor: '#854fff',
        secondaryColor: '#6b3fd4',
        position: 'right',
        backgroundColor: '#ffffff',
        fontColor: '#333333'
    }
};

// Function to generate or retrieve a unique chat ID
function getChatId() {
    let chatId = sessionStorage.getItem("chatId");
    if (!chatId) {
        chatId = "chat_" + Math.random().toString(36).substr(2, 9);
        sessionStorage.setItem("chatId", chatId);
    }
    return chatId;
}

// Close chat widget and show bubble
function closeChatWidget() {
    document.getElementById("chat-widget-container").style.display = "none";
    document.getElementById("chat-widget-button").style.display = "flex";
}

// Auto-scroll to bottom
function scrollChatToBottom() {
    const chatBody = document.getElementById("chat-widget-body");
    if (chatBody) {
        chatBody.scrollTop = chatBody.scrollHeight;
    }
}

// Initialize chat widget event listeners
function initChatWidget() {
    // Show chat widget and hide bubble
    const chatButton = document.getElementById("chat-widget-button");
    if (chatButton) {
        chatButton.addEventListener("click", function() {
            document.getElementById("chat-widget-container").style.display = "flex";
            document.getElementById("chat-widget-button").style.display = "none";
        });
    }

    // Send message to n8n webhook
    const sendButton = document.getElementById("chat-widget-send");
    if (sendButton) {
        sendButton.addEventListener("click", sendChatMessage);
    }

    // Allow sending message with Enter key
    const chatInput = document.getElementById("chat-widget-input");
    if (chatInput) {
        chatInput.addEventListener("keypress", function(event) {
            if (event.key === "Enter") {
                sendChatMessage();
            }
        });
    }
}

// Send chat message function
function sendChatMessage() {
    const chatInput = document.getElementById("chat-widget-input");
    let message = chatInput.value;

    if (message.trim() === "") return;

    let chatBody = document.getElementById("chat-widget-body");

    // Add user message
    let userMessageDiv = document.createElement("div");
    userMessageDiv.className = "user-message";
    let userMessage = document.createElement("p");
    userMessage.textContent = message;
    userMessageDiv.appendChild(userMessage);
    chatBody.appendChild(userMessageDiv);

    scrollChatToBottom();

    let chatId = getChatId();

    // Show typing indicator
    let typingDiv = document.createElement("div");
    typingDiv.className = "bot-message";
    let typingContainer = document.createElement("div");
    typingContainer.className = "typing-indicator";
    typingContainer.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
    typingDiv.appendChild(typingContainer);
    chatBody.appendChild(typingDiv);
    scrollChatToBottom();

    fetch('/api/chat/', {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": (typeof CSRF_TOKEN !== 'undefined' ? CSRF_TOKEN : '')
        },
        body: JSON.stringify({
            chatId: chatId,
            message: message,
            route: (window.ChatWidgetConfig.webhook && window.ChatWidgetConfig.webhook.route) || 'general'
        })
    })
    .then(response => {
        console.log("Response status:", response.status);
        if (!response.ok) {
            console.error("Webhook error - Status:", response.status);
        }
        return response.json();
    })
    .then(data => {
        console.log("Webhook response data:", data);

        // Remove typing indicator
        typingDiv.remove();

        // Add bot response
        let botMessageDiv = document.createElement("div");
        botMessageDiv.className = "bot-message";
        let botMessage = document.createElement("p");
        botMessage.innerHTML = data.output || "Sorry, I couldn't understand that. Please try again.";
        botMessageDiv.appendChild(botMessage);
        chatBody.appendChild(botMessageDiv);

        scrollChatToBottom();
    })
    .catch(error => {
        console.error("Error:", error);
        typingDiv.remove();

        let errorDiv = document.createElement("div");
        errorDiv.className = "bot-message";
        let errorMessage = document.createElement("p");
        errorMessage.textContent = "Sorry, something went wrong. Please try again later.";
        errorDiv.appendChild(errorMessage);
        chatBody.appendChild(errorDiv);

        scrollChatToBottom();
    });

    chatInput.value = "";
}

// Initialize chat widget when DOM is ready
document.addEventListener('DOMContentLoaded', initChatWidget);