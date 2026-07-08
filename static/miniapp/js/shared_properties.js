// shared_properties.js

// Countdown timer
function updateCountdown() {
    const expiresAt = new Date(window.sharedConfig.expiresAt);
    const now = new Date();
    const diff = expiresAt - now;

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

    let timeText = '';
    if (days > 0) {
        timeText = `${days}d ${hours}h ${minutes}m`;
    } else if (hours > 0) {
        timeText = `${hours}h ${minutes}m`;
    } else {
        timeText = `${minutes}m`;
    }

    // Update the DOM element (assuming id="expiresCountdown" is added to the expires p tag)
    const expiresElement = document.getElementById('expiresCountdown');
    if (expiresElement) {
        expiresElement.textContent = `Expires in: ${timeText}`;
    }
}

if (window.sharedConfig && window.sharedConfig.expiresAt) {
    updateCountdown();
    setInterval(updateCountdown, 60000);
}

// Currency System
class CurrencyConverter {
    constructor() {
        this.currentCurrency = 'NGN'; // NGN or USD
        this.exchangeRate = 1650; // Default NGN to USD rate
        this.isLoading = false;
        this.lastUpdated = null;
        this.init();
    }
    async init() {
        await this.fetchExchangeRate();
        this.setupEventListeners();
        this.updateUI();
    }
    async fetchExchangeRate() {
        try {
            const response = await fetch('https://api.exchangerate-api.com/v4/latest/USD');
            const data = await response.json();
            if (data && data.rates && data.rates.NGN) {
                this.exchangeRate = Math.round(data.rates.NGN);
                this.lastUpdated = new Date();
            }
        } catch (error) {
            console.log('Using fallback exchange rate:', this.exchangeRate);
        }
        this.updateExchangeRateDisplay();
    }
    setupEventListeners() {
        const toggleBtn = document.getElementById('currencyToggle');
        const minPriceInput = document.getElementById('minPriceInput');
        const maxPriceInput = document.getElementById('maxPriceInput');
        const filterForm = document.getElementById('filterForm');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                if (!this.isLoading) {
                    this.toggleCurrency();
                }
            });
        }
        if (minPriceInput) {
            minPriceInput.addEventListener('input', () => this.updateConversionHint());
        }
        if (maxPriceInput) {
            maxPriceInput.addEventListener('input', () => this.updateConversionHint());
        }
        if (filterForm) {
            filterForm.addEventListener('submit', (e) => {
                if (this.currentCurrency === 'USD') {
                    const minPrice = parseFloat(minPriceInput.value);
                    const maxPrice = parseFloat(maxPriceInput.value);
                    if (!isNaN(minPrice)) {
                        minPriceInput.value = Math.round(minPrice * this.exchangeRate);
                    }
                    if (!isNaN(maxPrice)) {
                        maxPriceInput.value = Math.round(maxPrice * this.exchangeRate);
                    }
                }
            });
        }
    }
    toggleCurrency() {
        this.isLoading = true;
        const toggleBtn = document.getElementById('currencyToggle');
        if (toggleBtn) {
            toggleBtn.classList.add('loading');
        }
        setTimeout(() => {
            this.currentCurrency = this.currentCurrency === 'NGN' ? 'USD' : 'NGN';
            this.updateUI();
            this.convertAllPrices();
            this.convertFilterInputs();
            this.isLoading = false;
            if (toggleBtn) {
                toggleBtn.classList.remove('loading');
            }
        }, 500);
    }
    updateUI() {
        const currencyDisplay = document.getElementById('currentCurrency');
        const priceRangeCurrency = document.getElementById('priceRangeCurrency');
        const currencyInfoText = document.getElementById('currencyInfoText');
        const priceRangeDisplay = document.getElementById('priceRangeDisplay');
        if (currencyDisplay) {
            currencyDisplay.textContent = this.currentCurrency === 'NGN' ? '₦ NGN' : '$ USD';
        }
        if (priceRangeCurrency) {
            priceRangeCurrency.textContent = this.currentCurrency === 'NGN' ? '₦' : '$';
        }
        if (currencyInfoText) {
            currencyInfoText.textContent = this.currentCurrency === 'NGN' ? 'Filtering in Nigerian Naira (₦)' : 'Filtering in US Dollars ($)';
        }
        if (priceRangeDisplay) {
            const minPrice = parseFloat(priceRangeDisplay.textContent.match(/[\d,]+/g)?.[0]?.replace(/,/g, ''));
            const maxPrice = parseFloat(priceRangeDisplay.textContent.match(/[\d,]+/g)?.[1]?.replace(/,/g, ''));
            if (!isNaN(minPrice) && !isNaN(maxPrice)) {
                if (this.currentCurrency === 'USD') {
                    priceRangeDisplay.textContent = `Range: $${(minPrice / this.exchangeRate).toLocaleString('en-US', {maximumFractionDigits: 0})} - $${(maxPrice / this.exchangeRate).toLocaleString('en-US', {maximumFractionDigits: 0})}`;
                } else {
                    priceRangeDisplay.textContent = `Range: ₦${minPrice.toLocaleString()} - ₦${maxPrice.toLocaleString()}`;
                }
            }
        }
    }
    updateExchangeRateDisplay() {
        const exchangeRateInfo = document.getElementById('exchangeRateInfo');
        if (exchangeRateInfo) {
            const timeStr = this.lastUpdated ? 
                `(Updated: ${this.lastUpdated.toLocaleTimeString()})` : '(Using default rate)';
            exchangeRateInfo.textContent = `Exchange rate: ₦${this.exchangeRate.toLocaleString()} = $1 USD ${timeStr}`;
        }
    }
    convertPrice(nairaPrice, toUSD = false) {
        if (!nairaPrice || nairaPrice === 'Price on Request') return nairaPrice;
        const numPrice = parseFloat(nairaPrice.toString().replace(/,/g, ''));
        if (isNaN(numPrice)) return nairaPrice;
        if (toUSD) {
            const usdPrice = numPrice / this.exchangeRate;
            return usdPrice < 1000 ? 
                `$${usdPrice.toLocaleString('en-US', {maximumFractionDigits: 0})}` :
                `$${(usdPrice/1000).toFixed(1)}K`;
        } else {
            return `₦${numPrice.toLocaleString()}`;
        }
    }
    convertAllPrices() {
        const priceTags = document.querySelectorAll('.price-tag[data-naira-price]');
        priceTags.forEach(tag => {
            const nairaPrice = tag.getAttribute('data-naira-price');
            const priceDisplay = tag.querySelector('.price-display');
            if (priceDisplay && nairaPrice) {
                tag.classList.add('loading');
                setTimeout(() => {
                    if (this.currentCurrency === 'USD') {
                        const convertedPrice = this.convertPrice(nairaPrice, true);
                        priceDisplay.innerHTML = `${convertedPrice}`;
                    } else {
                        priceDisplay.innerHTML = `₦${parseFloat(nairaPrice).toLocaleString()}`;
                    }
                    tag.classList.remove('loading');
                }, 300);
            }
        });
    }
    convertFilterInputs() {
        const minPriceInput = document.getElementById('minPriceInput');
        const maxPriceInput = document.getElementById('maxPriceInput');
        if (minPriceInput && minPriceInput.value) {
            const currentValue = parseFloat(minPriceInput.value.replace(/,/g, ''));
            if (!isNaN(currentValue)) {
                if (this.currentCurrency === 'USD') {
                    minPriceInput.value = Math.round(currentValue / this.exchangeRate);
                } else {
                    minPriceInput.value = Math.round(currentValue * this.exchangeRate);
                }
            }
        }
        if (maxPriceInput && maxPriceInput.value) {
            const currentValue = parseFloat(maxPriceInput.value.replace(/,/g, ''));
            if (!isNaN(currentValue)) {
                if (this.currentCurrency === 'USD') {
                    maxPriceInput.value = Math.round(currentValue / this.exchangeRate);
                } else {
                    maxPriceInput.value = Math.round(currentValue * this.exchangeRate);
                }
            }
        }
        this.updateConversionHint();
    }
    updateConversionHint() {
        const minPriceInput = document.getElementById('minPriceInput');
        const maxPriceInput = document.getElementById('maxPriceInput');
        const minPrice = minPriceInput ? minPriceInput.value : '';
        const maxPrice = maxPriceInput ? maxPriceInput.value : '';
        const hintElement = document.getElementById('priceConversionHint');
        const hintText = document.getElementById('conversionHintText');
        if (hintElement && hintText && (minPrice || maxPrice)) {
            let hintContent = '';
            if (this.currentCurrency === 'USD') {
                if (minPrice) {
                    const nairaEquivalent = (parseFloat(minPrice) * this.exchangeRate).toLocaleString();
                    hintContent += `$${parseFloat(minPrice).toLocaleString()} = ₦${nairaEquivalent}`;
                }
                if (maxPrice) {
                    const nairaEquivalent = (parseFloat(maxPrice) * this.exchangeRate).toLocaleString();
                    if (hintContent) hintContent += ' | ';
                    hintContent += `$${parseFloat(maxPrice).toLocaleString()} = ₦${nairaEquivalent}`;
                }
            } else {
                if (minPrice) {
                    const usdEquivalent = (parseFloat(minPrice) / this.exchangeRate).toLocaleString('en-US', {maximumFractionDigits: 0});
                    hintContent += `₦${parseFloat(minPrice).toLocaleString()} = $${usdEquivalent}`;
                }
                if (maxPrice) {
                    const usdEquivalent = (parseFloat(maxPrice) / this.exchangeRate).toLocaleString('en-US', {maximumFractionDigits: 0});
                    if (hintContent) hintContent += ' | ';
                    hintContent += `₦${parseFloat(maxPrice).toLocaleString()} = $${usdEquivalent}`;
                }
            }
            hintText.textContent = hintContent;
            hintElement.classList.remove('hidden');
        } else if (hintElement) {
            hintElement.classList.add('hidden');
        }
    }
}

// Initialize currency converter
let currencyConverter;
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        currencyConverter = new CurrencyConverter();
    });
} else {
    currencyConverter = new CurrencyConverter();
}

// Map functionality
let map = null;
        
function closeMapModal() {
    if (map) {
        map.closePopup();
    }
}

function initMap() {
    const mapContainer = document.getElementById('mapContainer');
    if (!mapContainer || mapContainer.classList.contains('hidden') || !window.sharedConfig) {
        return;
    }
    const mapElement = document.getElementById('map');
    if (!mapElement) return;
    map = L.map(mapElement).setView([6.5244, 3.3792], 12); // Default to Lagos, Nigeria
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    const properties = window.sharedConfig.propertyData || [];

    let bounds = [];
    properties.forEach(property => {
        if (property.lat && property.lng) {
            const marker = L.marker([property.lat, property.lng]).addTo(map);
            const price = property.min_price ? 
                (currencyConverter && currencyConverter.currentCurrency === 'USD' ? 
                    currencyConverter.convertPrice(property.min_price, true) : 
                    `₦${parseFloat(property.min_price).toLocaleString()}`) : 
                'Price on Request';
            marker.bindPopup(`
                <div class="p-2 max-w-xs">
                    <h3 class="font-bold text-sm">${property.name}</h3>
                    <p class="text-xs text-gray-600">${property.address}</p>
                    <p class="text-xs font-semibold">${price}</p>
                    <button onclick="showPropertyModal(${property.id})"
                            class="mt-2 text-white px-2 py-1 rounded text-xs" style="background: var(--ink, #161B33);">
                        View Details
                    </button>
                </div>
            `);
            bounds.push([property.lat, property.lng]);
        }
    });

    if (bounds.length > 0) {
        map.fitBounds(bounds, { padding: [50, 50] });
    }
}

// Toggle map view
function setupMapToggle() {
    const toggleMapBtn = document.getElementById('toggleMapBtn');
    const mapContainer = document.getElementById('mapContainer');
    const propertyGrid = document.querySelector('.property-grid');
    if (!toggleMapBtn || !mapContainer || !propertyGrid) return;
    toggleMapBtn.addEventListener('click', () => {
        if (mapContainer.classList.contains('hidden')) {
            mapContainer.classList.remove('hidden');
            propertyGrid.classList.add('hidden');
            toggleMapBtn.innerHTML = '<i class="fas fa-th-large mr-2"></i><span>Toggle Grid View</span>';
            initMap();
        } else {
            mapContainer.classList.add('hidden');
            propertyGrid.classList.remove('hidden');
            toggleMapBtn.innerHTML = '<i class="fas fa-map-marked-alt mr-2"></i><span>Toggle Map View</span>';
            if (map) {
                map.remove();
                map = null;
            }
        }
    });
}

// Mobile menu functionality
function setupMobileMenu() {
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const closeMobileMenu = document.getElementById('closeMobileMenu');
    const filterSidebar = document.getElementById('filterSidebar');
    const mobileFilterOverlay = document.getElementById('mobileFilterOverlay');
    if (!mobileMenuBtn || !closeMobileMenu || !filterSidebar || !mobileFilterOverlay) return;

    function openMobileFilter() {
        filterSidebar.classList.add('open');
        mobileFilterOverlay.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }
    function closeMobileFilter() {
        filterSidebar.classList.remove('open');
        mobileFilterOverlay.classList.add('hidden');
        document.body.style.overflow = '';
    }
    mobileMenuBtn.addEventListener('click', openMobileFilter);
    closeMobileMenu.addEventListener('click', closeMobileFilter);
    mobileFilterOverlay.addEventListener('click', closeMobileFilter);
    window.addEventListener('resize', function() {
        if (window.innerWidth >= 1024) {
            closeMobileFilter();
        }
    });
}

// Property image gallery functionality
let propertyImages = window.sharedConfig ? window.sharedConfig.propertyImages : {};
let propertyImageIndices = window.sharedConfig ? window.sharedConfig.propertyImageIndices : {};

function changePropertyImage(propertyId, direction) {
    const images = propertyImages[propertyId];
    if (!images || images.length <= 1) return;
    propertyImageIndices[propertyId] = (propertyImageIndices[propertyId] + direction + images.length) % images.length;
    const imgElement = document.querySelector(`img[data-property-id="${propertyId}"]`);
    if (imgElement) {
        imgElement.style.opacity = '0.7';
        setTimeout(() => {
            imgElement.src = images[propertyImageIndices[propertyId]];
            imgElement.style.opacity = '1';
        }, 200);
    }
}

// Enhanced Property modal functionality with currency support
let currentModalImageIndex = 0;
let currentModalImages = [];
        
async function showPropertyModal(propertyId) {
    closeMapModal();
    const modal = document.getElementById('propertyModal');
    const modalTitle = document.getElementById('modalTitle');
    const modalContent = document.getElementById('modalContent');
    if (!modal || !modalTitle || !modalContent) return;
            
    modalContent.innerHTML = `
        <div class="flex items-center justify-center py-12">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2" style="border-color: var(--ink);"></div>
            <span class="ml-3" style="color: var(--slate-500);">Loading property details...</span>
        </div>
    `;
            
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
            
    try {
        const response = await fetch(`/api/properties/${propertyId}/`);
        if (!response.ok) throw new Error('Failed to fetch property details');
        const property = await response.json();
                
        currentModalImages = property.images || [];
        currentModalImageIndex = 0;
                
        modalTitle.innerHTML = `<span>${property.name || 'Property Details'}</span>`;

        const listName = (window.sharedConfig && window.sharedConfig.listName) || 'this shared list';

        modalContent.innerHTML = `
            <div class="space-y-6">
                <!-- Image Gallery -->
                <div class="modal-section">
                    ${property.images?.length > 0 ? `
                        <div class="modal-image-container">
                            <img src="${property.images[0]}" alt="${property.name}" class="modal-image" id="modalMainImage">
                            ${property.images.length > 1 ? `
                                <button class="gallery-nav prev" onclick="changeModalImage(-1)">
                                    <i class="fas fa-chevron-left"></i>
                                </button>
                                <button class="gallery-nav next" onclick="changeModalImage(1)">
                                    <i class="fas fa-chevron-right"></i>
                                </button>
                                <div class="absolute bottom-4 left-1/2 transform -translate-x-1/2">
                                    <div class="bg-black bg-opacity-50 text-white px-3 py-1 rounded-full text-sm backdrop-blur-sm">
                                        <span id="imageCounter">1</span> / ${property.images.length}
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                    ` : `
                        <div class="w-full h-64 flex items-center justify-center" style="background: var(--slate-100); border-radius: var(--r-md);">
                            <div class="text-center">
                                <i class="fas fa-image text-4xl mb-2" style="color: var(--slate-400);"></i>
                                <p style="color: var(--slate-500);">No images available</p>
                            </div>
                        </div>
                    `}
                </div>
                <!-- Property Information -->
                <div class="modal-section">
                    <h3 class="modal-section-title">
                        <i class="fas fa-info-circle"></i>
                        Property Information
                    </h3>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div class="info-tile">
                            <div class="info-label">Address</div>
                            <div class="info-value">${property.address || 'Not specified'}</div>
                        </div>
                        <div class="info-tile">
                            <div class="info-label">Luxury Status</div>
                            <div class="info-value">
                                ${property.luxury_status === 'luxurious' ?
                                    '<span style="color: var(--gold);"><i class="fas fa-crown mr-1"></i>Luxurious</span>' :
                                    'Standard'
                                }
                            </div>
                        </div>
                        <div class="info-tile">
                            <div class="info-label">Completion Date</div>
                            <div class="info-value">${property.completion_date || 'Not specified'}</div>
                        </div>
                    </div>
                </div>
                <!-- Description -->
                ${property.description ? `
                    <div class="modal-section">
                        <h3 class="modal-section-title">
                            <i class="fas fa-align-left"></i>
                            Description
                        </h3>
                        <div class="info-tile">
                            <p style="color: var(--ink); line-height: 1.6;">${property.description}</p>
                        </div>
                    </div>
                ` : ''}
                <!-- Configurations with Currency -->
                ${property.configurations?.length > 0 ? `
                    <div class="modal-section">
                        <h3 class="modal-section-title">
                            <i class="fas fa-bed"></i>
                            Available Configurations
                        </h3>
                        <div class="space-y-2">
                            ${property.configurations.map(config => {
                                let priceDisplay = 'Price on request';
                                if (config.price && config.price !== 'TBD') {
                                    // Clean the price string by removing '₦' and commas
                                    const cleanPrice = parseFloat(config.price.replace('₦', '').replace(/,/g, ''));
                                    if (!isNaN(cleanPrice)) {
                                        const nairaPrice = cleanPrice;
                                        if (currencyConverter && currencyConverter.currentCurrency === 'USD') {
                                            const usdPrice = nairaPrice / currencyConverter.exchangeRate;
                                            priceDisplay = usdPrice < 1000 ?
                                                `$${usdPrice.toLocaleString('en-US', {maximumFractionDigits: 0})}` :
                                                `$${(usdPrice/1000).toFixed(1)}K`;
                                        } else {
                                            priceDisplay = `₦${nairaPrice.toLocaleString()}`;
                                        }
                                    }
                                }
                                return `
                                    <div class="config-row">
                                        <div style="display:flex; align-items:center; gap:16px;">
                                            <span style="display:flex; align-items:center; gap:4px; color: var(--slate-600);">
                                                <i class="fas fa-bed"></i>
                                                <strong style="color: var(--ink);">${config.bedrooms || 'N/A'}</strong> Bed${(config.bedrooms && config.bedrooms !== 1) ? 's' : ''}
                                            </span>
                                            <span style="display:flex; align-items:center; gap:4px; color: var(--slate-600);">
                                                <i class="fas fa-bath"></i>
                                                <strong style="color: var(--ink);">${config.bathrooms || 'N/A'}</strong> Bath${(config.bathrooms && config.bathrooms !== 1) ? 's' : ''}
                                            </span>
                                            <span style="color: var(--slate-600);">
                                                <strong style="color: var(--ink);">${config.square_footage || 'N/A'}</strong> sq ft
                                            </span>
                                        </div>
                                        <div style="font-weight:600; font-variant-numeric: tabular-nums; color: var(--ink);">
                                            ${priceDisplay}
                                        </div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>
                ` : ''}
                <!-- Amenities -->
                ${property.amenities?.length > 0 ? `
                    <div class="modal-section">
                        <h3 class="modal-section-title">
                            <i class="fas fa-star"></i>
                            Amenities & Features
                        </h3>
                        <div class="flex flex-wrap gap-2">
                            ${property.amenities.map(amenity => `
                                <span class="px-3 py-1 rounded-full text-xs font-medium" style="background: var(--slate-100); color: var(--ink);">${amenity}</span>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}
                <!-- Contact Section -->
                <div class="modal-section" style="margin-bottom: 0;">
                    <h3 class="modal-section-title">
                        <i class="fas fa-phone"></i>
                        Contact Information
                    </h3>
                    <div class="info-tile" style="text-align: center;">
                        <p style="color: var(--slate-600); margin-bottom: 14px;">Interested in this property? Get in touch with us!</p>
                        <a href="https://wa.me/${property.contact?.split(' - ')[1] || '2348000000000'}?text=${encodeURIComponent(`Hi! I'm interested in ${property.name} from the shared property list: ${listName}`)}"
                           class="whatsapp-button"
                           target="_blank" rel="noopener">
                            <i class="fab fa-whatsapp"></i>
                            Contact via WhatsApp
                        </a>
                        <p style="margin-top: 12px; font-size: 12.5px; color: var(--slate-500);">
                            <i class="fas fa-clock mr-1"></i>
                            We typically respond within minutes
                        </p>
                    </div>
                </div>
            </div>
        `;
                
    } catch (error) {
        console.error('Error fetching property details:', error);
        modalContent.innerHTML = `
            <div class="text-center py-12">
                <div class="bg-red-50 border border-red-200 p-6" style="border-radius: var(--r-md);">
                    <i class="fas fa-exclamation-triangle text-red-500 text-4xl mb-4"></i>
                    <h3 class="text-lg font-semibold text-red-800 mb-2">Error Loading Property</h3>
                    <p class="text-red-600 mb-4">We couldn't load the property details. Please try again.</p>
                    <button onclick="closePropertyModal()" 
                            class="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 transition-all">
                        Close
                    </button>
                </div>
            </div>
        `;
    }
}

// PDF download functionality
async function downloadPropertyPDF(propertyId) {
    if (!window.sharedConfig || !window.sharedConfig.pdfUrlTemplate) return;
    try {
        const url = window.sharedConfig.pdfUrlTemplate.replace('0', propertyId);
        console.log(`${url}`);
        const response = await fetch(url);
                
        if (!response.ok) {
            throw new Error('Failed to generate PDF');
        }
                
        const blob = await response.blob();
        const urlBlob = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = urlBlob;
        a.download = `property-${propertyId}-details.pdf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(urlBlob);
        document.body.removeChild(a);
                
    } catch (error) {
        alert('Error downloading PDF: ' + error.message);
    }
}
        
function closePropertyModal() {
    const modal = document.getElementById('propertyModal');
    if (modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = '';
    }
}
        
function changeModalImage(direction) {
    if (!currentModalImages || currentModalImages.length <= 1) return;
    currentModalImageIndex = (currentModalImageIndex + direction + currentModalImages.length) % currentModalImages.length;
    const modalImage = document.getElementById('modalMainImage');
    const imageCounter = document.getElementById('imageCounter');
    if (modalImage) {
        modalImage.style.opacity = '0.7';
        setTimeout(() => {
            modalImage.src = currentModalImages[currentModalImageIndex];
            modalImage.style.opacity = '1';
            if (imageCounter) {
                imageCounter.textContent = currentModalImageIndex + 1;
            }
        }, 200);
    }
}
        
// Close modal when clicking outside
function setupModalEvents() {
    const propertyModal = document.getElementById('propertyModal');
    if (propertyModal) {
        propertyModal.addEventListener('click', function(e) {
            if (e.target === this) {
                closePropertyModal();
            }
        });
    }
        
    // Handle keyboard navigation
    document.addEventListener('keydown', function(e) {
        const modal = document.getElementById('propertyModal');
        if (!modal || modal.classList.contains('hidden')) return;
        if (e.key === 'Escape') {
            closePropertyModal();
        } else if (e.key === 'ArrowLeft') {
            changeModalImage(-1);
        } else if (e.key === 'ArrowRight') {
            changeModalImage(1);
        }
    });
}

// Slider functionality (IIFE)
(function () {
    const minRange = document.getElementById('sqft-min-range');
    const maxRange = document.getElementById('sqft-max-range');
    const minHidden = document.getElementById('min_square_footage');
    const maxHidden = document.getElementById('max_square_footage');
    const minReadout = document.getElementById('sqft-min-readout');
    const maxReadout = document.getElementById('sqft-max-readout');
    const rangeFill = document.getElementById('sqft-range-fill');

    if (!minRange || !maxRange || !minHidden || !maxHidden || !minReadout || !maxReadout || !rangeFill) return;

    const step = parseInt(minRange.step || '5', 10);
    const minGap = step; // keep handles from overlapping by at least one step

    function format(n) { return Number(n).toLocaleString(); }

    function clamp() {
        let minVal = parseInt(minRange.value, 10);
        let maxVal = parseInt(maxRange.value, 10);
        if (maxVal - minVal < minGap) {
            if (document.activeElement === minRange) {
                minVal = maxVal - minGap;
                minRange.value = minVal;
            } else {
                maxVal = minVal + minGap;
                maxRange.value = maxVal;
            }
        }
        sync();
    }

    function sync() {
        const min = parseInt(minRange.min, 10);
        const max = parseInt(maxRange.max, 10);
        const minVal = parseInt(minRange.value, 10);
        const maxVal = parseInt(maxRange.value, 10);

        if (minReadout) minReadout.textContent = format(minVal);
        if (maxReadout) maxReadout.textContent = format(maxVal);
        if (minHidden) minHidden.value = minVal;
        if (maxHidden) maxHidden.value = maxVal;

        const pctMin = ((minVal - min) / (max - min)) * 100;
        const pctMax = ((maxVal - min) / (max - min)) * 100;
        rangeFill.style.left = pctMin + '%';
        rangeFill.style.right = (100 - pctMax) + '%';
    }

    function initFromHidden() {
        const minProvided = parseInt(minHidden.value || minRange.min, 10);
        const maxProvided = parseInt(maxHidden.value || maxRange.max, 10);
        minRange.value = isNaN(minProvided) ? minRange.min : minProvided;
        maxRange.value = isNaN(maxProvided) ? maxRange.max : maxProvided;
        sync();
    }

    minRange.addEventListener('input', clamp);
    maxRange.addEventListener('input', clamp);
    initFromHidden();
})();

// Initialize all setups on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        setupMapToggle();
        setupMobileMenu();
        setupModalEvents();
    });
} else {
    setupMapToggle();
    setupMobileMenu();
    setupModalEvents();
}