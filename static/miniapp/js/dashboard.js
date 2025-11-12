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
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);
    L.control.zoom({ position: 'topright' }).addTo(map);
    L.control.scale().addTo(map);
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
        maxClusterRadius: 40
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
            iconSize: [44, 44],
            iconAnchor: [22, 22]
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
    console.log('Creating modal for property:', property.id, 'Images:', property.images);
    currentImageIndex = 0;

    const images = Array.isArray(property.images) && property.images.length > 0 
        ? property.images 
        : [property.thumbnail || 'https://via.placeholder.com/200'];
    
    const configurationsHTML = property.configurations.length > 0
        ? property.configurations.map(config => {
            let priceDisplay = config.price || 'TBD';
            if (config.price && config.price !== 'TBD') {
                const cleanPrice = parseFloat(config.price.replace(/[₦,]/g, '')) || 0;
                priceDisplay = currencyConverter.currentCurrency === 'USD'
                    ? `$${currencyConverter.convert(cleanPrice, 'USD').toLocaleString('en-US', { maximumFractionDigits: 0 })}`
                    : `₦${cleanPrice.toLocaleString()}`;
            }
            return `
                <div class="unit-item">
                    <div class="unit-header">
                        <h3 class="unit-name">${config.type}</h3>
                        <div class="unit-price-tag">${priceDisplay}</div>
                    </div>
                    <div class="unit-details">
                        <span class="unit-detail"><i class="fas fa-bed"></i> ${config.bedrooms || 0} Bed</span>
                        <span class="unit-detail"><i class="fas fa-bath"></i> ${config.bathrooms || 0} Bath</span>
                        <span class="unit-detail"><i class="fas fa-vector-square"></i> ${(config.square_footage || 0).toLocaleString()} sq ft</span>
                    </div>
                </div>
            `;
        }).join('')
        : '<div class="no-configs-message">No configurations available</div>';
    
    const phoneNumber = extractPhoneNumber(property.contact);
    console.log('Extracted phone number:', phoneNumber);
    const whatsappNumber = formatWhatsAppNumber(phoneNumber);
    console.log('Formatted WhatsApp number:', whatsappNumber);
    const whatsappMessage = encodeURIComponent(`Hi! I'm interested in the property: ${property.name} at ${property.address}. Could you please provide more information?`);
    const whatsappLink = `https://wa.me/${whatsappNumber}?text=${whatsappMessage}`;
    console.log('WhatsApp link:', whatsappLink);
    
    return `
        <div class="elegant-modal">
            <!-- Close Button -->
            <button onclick="closeModal()" class="modal-close-button">×</button>

            <!-- Image Carousel -->
            <div class="modal-carousel">
                <img src="${images[currentImageIndex]}" alt="${property.name}" id="galleryImage" class="carousel-img"/>
                ${images.length > 1 ? `
                <button class="carousel-arrow left" onclick="changeImage(-1, ${property.id})">
                    <i class="fas fa-chevron-left"></i>
                </button>
                <button class="carousel-arrow right" onclick="changeImage(1, ${property.id})">
                    <i class="fas fa-chevron-right"></i>
                </button>
                <div class="carousel-dots">
                    ${images.map((_, idx) => `<span class="${idx === currentImageIndex ? 'active' : ''}" onclick="setImage(${idx}, ${property.id})"></span>`).join('')}
                </div>
                ` : ''}
            </div>

            <!-- Content Area -->
            <div class="modal-body">
                <!-- Title & Meta -->
                <div class="property-title-section">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <h1 class="property-title">${property.name}</h1>
                        ${window.isInternalUser ? `
                            <label class="inline-flex items-center bg-white/95 backdrop-blur-sm px-3 py-2 rounded-lg cursor-pointer shadow-sm hover:shadow-md transition-shadow">
                                <input
                                    type="checkbox"
                                    class="dashboard-property-checkbox form-checkbox h-4 w-4 text-blue-600 rounded focus:ring-blue-500 focus:ring-2"
                                    value="${property.id}"
                                    ${selectedPropertyIds.has(property.id.toString()) ? 'checked' : ''}
                                    onchange="togglePropertySelection(this)"
                                >
                                <span class="ml-2 text-sm font-semibold text-gray-700">Select for Compare</span>
                            </label>
                        ` : ''}
                    </div>
                    <div class="property-meta-row">
                        <span class="meta-location"><i class="fas fa-map-marker-alt"></i> ${property.address}</span>
                        ${!property.is_exact_location ? '<span class="meta-approximate">Approx</span>' : ''}
                    </div>
                    <div class="meta-badges">
                        <span class="badge badge-luxury">${property.luxury_status}</span>
                        <span class="badge">${property.completion_date}</span>
                    </div>
                </div>

                ${!property.is_exact_location ? `
                <div class="location-privacy-notice">
                    <div class="notice-content">
                        <i class="fas fa-shield-alt notice-icon"></i>
                        <div>
                            <strong>Location Privacy Active</strong>
                            <p>Exact address provided upon inquiry</p>
                        </div>
                    </div>
                    <button onclick="requestLocationUnlock(${property.id})" id="unlockBtn${property.id}" class="btn-unlock-location">
                        <i class="fas fa-unlock-alt"></i> Unlock
                    </button>
                </div>
                ` : ''}

                <!-- Description -->
                <div class="property-description">
                    <p>${property.description}</p>
                </div>

                <!-- Units -->
                ${property.configurations.length > 0 ? `
                <div class="property-section">
                    <h2 class="section-heading">Available Units</h2>
                    <div class="units-grid">${configurationsHTML}</div>
                </div>
                ` : ''}

                <!-- Amenities -->
                ${property.amenities.length > 0 ? `
                <div class="property-section">
                    <h2 class="section-heading">Amenities & Features</h2>
                    <div class="amenities-wrap">
                        ${property.amenities.map(a => `<div class="amenity-pill"><i class="fas fa-check-circle"></i> ${a}</div>`).join('')}
                    </div>
                </div>
                ` : ''}

                <!-- Construction Progress (Only shown to users with exact location access) -->
                ${property.progress_updates && property.progress_updates.length > 0 ? `
                <div class="property-section">
                    <h2 class="section-heading"><i class="fas fa-hard-hat" style="margin-right: 8px;"></i>Construction Progress</h2>
                    <div class="progress-timeline">
                        ${property.progress_updates.map((update) => `
                            <div class="progress-card ${update.is_latest ? 'latest-update' : ''}">
                                ${update.is_latest ? `
                                    <div class="latest-badge">
                                        <i class="fas fa-check-circle"></i> Latest Update
                                    </div>
                                ` : ''}
                                <div class="progress-header">
                                    <div class="progress-info">
                                        <h3 class="progress-stage">${update.stage}</h3>
                                        <p class="progress-date">
                                            <i class="far fa-calendar"></i>
                                            ${new Date(update.update_date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
                                        </p>
                                    </div>
                                    <div class="progress-percent">
                                        <div class="percent-number">${update.progress_percentage}%</div>
                                        <div class="percent-label">Complete</div>
                                    </div>
                                </div>
                                <div class="progress-bar-container">
                                    <div class="progress-bar-fill" style="width: ${update.progress_percentage}%"></div>
                                </div>
                                ${update.description ? `
                                    <p class="progress-description">${update.description}</p>
                                ` : ''}
                                ${update.uploaded_by ? `
                                    <p class="progress-uploader">
                                        <i class="fas fa-user-circle"></i> Updated by ${update.uploaded_by}
                                    </p>
                                ` : ''}
                                ${update.images && update.images.length > 0 ? `
                                    <div class="progress-images-section">
                                        <p class="progress-images-title">
                                            <i class="fas fa-images"></i> Progress Photos (${update.images.length})
                                        </p>
                                        <div class="progress-images-grid">
                                            ${update.images.slice(0, 4).map((img, imgIndex) => `
                                                <div class="progress-image-item" onclick="window.open('${img}', '_blank')">
                                                    <img src="${img}" alt="Progress ${imgIndex + 1}" loading="lazy">
                                                    ${imgIndex === 3 && update.images.length > 4 ? `
                                                        <div class="progress-image-overlay">
                                                            +${update.images.length - 4} more
                                                        </div>
                                                    ` : ''}
                                                </div>
                                            `).join('')}
                                        </div>
                                    </div>
                                ` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>
                ` : ''}

                <!-- Action Buttons -->
                <div class="action-buttons">
                    <button onclick="showContact()" class="btn btn-contact">
                        <i class="fas fa-phone-alt"></i> Contact Agent
                    </button>
                    <button onclick="downloadBrochure('${property.brochure}')" class="btn btn-download">
                        <i class="fas fa-file-download"></i> Brochure
                    </button>
                </div>

                <!-- Contact Info -->
                <div id="contactDisplay" class="contact-info-panel">
                    <div class="contact-agent">
                        <i class="fas fa-user-circle"></i>
                        <span>${property.contact}</span>
                    </div>
                    <a href="${whatsappLink}" target="_blank" class="btn-whatsapp-contact">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893A11.821 11.821 0 0020.465 3.516"/>
                        </svg>
                        Message on WhatsApp
                    </a>
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

function showContact() {
    console.log('showContact called');
    const contactDisplay = document.getElementById('contactDisplay');
    console.log('contactDisplay element:', contactDisplay);
    if (contactDisplay) {
        contactDisplay.classList.add('active');
        console.log('Added active class');
    } else {
        console.error('contactDisplay element not found');
    }
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