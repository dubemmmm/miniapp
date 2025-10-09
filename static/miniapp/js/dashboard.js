// dashboard.js

let map, properties = [], filteredProperties = [];
let currentImageIndex = 0;
let currencyConverter;

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
        updateMap();
        updatePropertyCount();
    } catch (error) {
        console.error('Error fetching properties:', error);
        alert('Error fetching properties. Please try again later.');
    }
}

function updateMap() {
    map.eachLayer(layer => {
        if (layer instanceof L.Marker || layer instanceof L.MarkerClusterGroup) {
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
        const icon = L.divIcon({
            html: `<div class="custom-marker"><img src="${property.thumbnail || 'https://via.placeholder.com/40'}" alt="${property.name}"/></div>`,
            className: 'custom-marker-container',
            iconSize: [44, 44],
            iconAnchor: [22, 22]
        });
        const marker = L.marker([property.latitude, property.longitude], { icon });
        marker.on('click', () => showPropertyModal(property));
        cluster.addLayer(marker);
        validMarkers.push(marker);
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
    
    const amenities = property.amenities.map(a => 
        `<span class="bg-blue-50 text-blue-700 px-2 md:px-3 py-1 rounded-full text-xs md:text-sm border border-blue-200">${a}</span>`
    ).join('');
    
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
                <div class="configuration-card">
                    <div class="configuration-header">
                        <div class="configuration-type">${config.type}</div>
                        <div class="configuration-price">${priceDisplay}</div>
                    </div>
                    <div class="configuration-details">
                        <div class="detail-item">
                            <div class="detail-label">Bedrooms</div>
                            <div class="detail-value"><i class="fas fa-bed mr-1"></i>${config.bedrooms || 0}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Bathrooms</div>
                            <div class="detail-value"><i class="fas fa-bath mr-1"></i>${config.bathrooms || 0}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Square Feet</div>
                            <div class="detail-value"><i class="fas fa-ruler-combined mr-1"></i>${(config.square_footage || 0).toLocaleString()}</div>
                        </div>
                    </div>
                </div>
            `;
        }).join('')
        : '<div class="text-center text-gray-500 py-8">No configurations available</div>';
    
    const phoneNumber = extractPhoneNumber(property.contact);
    const whatsappNumber = formatWhatsAppNumber(phoneNumber);
    const whatsappMessage = encodeURIComponent(`Hi! I'm interested in the property: ${property.name} at ${property.address}. Could you please provide more information?`);
    const whatsappLink = `https://wa.me/${whatsappNumber}?text=${whatsappMessage}`;
    
    return `
        <div class="bg-white rounded-lg p-8 shadow-lg">
            <h2 class="text-xl md:text-2xl font-bold text-gray-800 mb-4">${property.name}</h2>
            <div class="image-gallery">
                <img src="${images[currentImageIndex]}" alt="${property.name}" id="galleryImage"/>
                ${images.length > 1 ? `
                <button class="gallery-nav prev" onclick="changeImage(-1, ${property.id})"><i class="fas fa-chevron-left"></i></button>
                <button class="gallery-nav next" onclick="changeImage(1, ${property.id})"><i class="fas fa-chevron-right"></i></button>
                <div class="gallery-indicators">
                    ${images.map((_, idx) => 
                        `<div class="gallery-indicator ${idx === currentImageIndex ? 'active' : ''}" 
                              onclick="setImage(${idx}, ${property.id})"></div>`
                    ).join('')}
                </div>` : ''}
            </div>
            <div class="space-y-2 mb-6">
                <p class="text-gray-600 text-sm md:text-base flex items-center"><i class="fas fa-map-marker-alt mr-2 text-blue-500"></i><strong>Address:</strong> ${property.address}</p>
                <p class="text-gray-700 text-sm md:text-base"><strong>Description:</strong>${property.description}</p>
                <p class="text-gray-700 text-sm md:text-base"><strong>Luxury Status:</strong> ${property.luxury_status}</p>
                <p class="text-gray-700 text-sm md:text-base"><strong>Completion Date:</strong> ${property.completion_date}</p>
            </div>
            
            <div class="configurations-section">
                <h3 class="text-lg font-semibold text-gray-800 mb-2">Available Types</h3>
                <div class="configurations-grid">
                    ${configurationsHTML}
                </div>
            </div>
            
            <div class="mb-6">
                <span class="block text-xs md:text-sm text-gray-600 mb-2">Amenities</span>
                <div class="flex flex-wrap gap-2">${amenities}</div>
            </div>
            <div class="flex gap-3 md:gap-4">
                <button onclick="showContact()" class="flex-1 py-2 md:py-3 bg-gray-800 text-white rounded-lg text-sm md:text-base font-medium hover:bg-gray-700"><i class="fas fa-phone mr-2"></i>Contact Agent</button>
                <button onclick="downloadBrochure('${property.brochure}')" class="flex-1 py-2 md:py-3 bg-gray-200 text-gray-800 rounded-lg text-sm md:text-base font-medium hover:bg-gray-300"><i class="fas fa-download mr-2"></i>Download Brochure</button>
            </div>
            <div id="contactDisplay" class="contact-display">
                <div class="contact-info">
                    <span>Contact: ${property.contact}</span>
                    <a href="${whatsappLink}" target="_blank" class="whatsapp-button">
                        <svg class="whatsapp-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
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
    const contactDisplay = document.getElementById('contactDisplay');
    if (contactDisplay) {
        contactDisplay.classList.add('active');
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
    // ✅ Get selected completion date (YYYY-MM-DD)
    const completionDateInputEl = document.getElementById('completionDate');
    const completionDateSelectedStr = completionDateInputEl && completionDateInputEl.value ? completionDateInputEl.value : null;
    const completionDateSelected = completionDateSelectedStr ? new Date(completionDateSelectedStr) : null;
    console.log(completionDateSelected)
    if (completionDateSelected) completionDateSelected.setHours(0, 0, 0, 0);

    // Convert input prices to NGN (base currency) for filtering
    const minPriceNGN = currencyConverter.currentCurrency === 'USD'
        ? currencyConverter.convert(minPriceInput, 'NGN')
        : minPriceInput;
    const maxPriceNGN = currencyConverter.currentCurrency === 'USD'
        ? currencyConverter.convert(maxPriceInput, 'NGN')
        : maxPriceInput;

    filteredProperties = properties.filter(p => {
        // ✅ Completion date check (only if user selected a date)
    let matchesCompletionDate = true;
        if (completionDateSelected) {
            if (!p.completion_date) {
                matchesCompletionDate = false; // no date -> exclude when filter is active
            } else {
                const propDate = new Date(p.completion_date);
                if (isNaN(propDate.getTime())) {
                    matchesCompletionDate = false; // invalid date -> exclude when filter is active
                } else {
                    propDate.setHours(0, 0, 0, 0);
                    matchesCompletionDate = propDate.getTime() <= completionDateSelected.getTime();
                }
            }
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
    const completionDateInputEl = document.getElementById('completionDate');
    
    if (minPriceInput) minPriceInput.value = '';
    if (maxPriceInput) maxPriceInput.value = '';
    if (minBedroomsInput) minBedroomsInput.value = '';
    if (maxBedroomsInput) maxBedroomsInput.value = '';
    if (minBathroomsInput) minBathroomsInput.value = '';
    if (maxBathroomsInput) maxBathroomsInput.value = '';
    if (luxuryStatusInput) luxuryStatusInput.value = 'all';
    if (searchInputSidebar) searchInputSidebar.value = '';
    if (completionDateInputEl) completionDateInputEl.value = '';
    
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
    
    const searchInput = document.getElementById('searchInput');
    const searchInputSidebar = document.getElementById('searchInputSidebar');
    const luxuryStatus = document.getElementById('luxuryStatus');
    const minBedrooms = document.getElementById('minBedrooms');
    const maxBedrooms = document.getElementById('maxBedrooms');
    const minBathrooms = document.getElementById('minBathrooms');
    const maxBathrooms = document.getElementById('maxBathrooms');
    const minPrice = document.getElementById('minPrice');
    const maxPrice = document.getElementById('maxPrice');
    const completionDate = document.getElementById('completionDate');
    
    if (searchInput) searchInput.addEventListener('input', handleSearch);
    if (searchInputSidebar) searchInputSidebar.addEventListener('input', handleSearch);
    if (luxuryStatus) luxuryStatus.addEventListener('change', updateLuxuryStatusDisplay);
    if (minBedrooms) minBedrooms.addEventListener('input', () => updateRangeDisplay('Bedrooms'));
    if (maxBedrooms) maxBedrooms.addEventListener('input', () => updateRangeDisplay('Bedrooms'));
    if (minBathrooms) minBathrooms.addEventListener('input', () => updateRangeDisplay('Bathrooms'));
    if (maxBathrooms) maxBathrooms.addEventListener('input', () => updateRangeDisplay('Bathrooms'));
    if (minPrice) minPrice.addEventListener('input', updatePriceDisplay);
    if (maxPrice) maxPrice.addEventListener('input', updatePriceDisplay);
    if (completionDate) completionDate.addEventListener('change', () => {
        const completionDateDisplay = document.getElementById('completionDateDisplay');
        if (completionDateDisplay) {
            completionDateDisplay.textContent = completionDate.value ? `By ${completionDate.value}` : 'Any date';
        }
    });
    
    if (searchBox) {
        searchBox.style.left = (window.innerWidth / 2 - (window.innerWidth < 768 ? window.innerWidth / 2 - 10 : 150)) + 'px';
        searchBox.style.top = '10px';
    }
    
    const closeButton = document.getElementById('modalCloseButton');
    if (closeButton) {
        closeButton.addEventListener('click', closeModal);
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