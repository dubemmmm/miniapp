// landing.js

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
        toggleBtn.addEventListener('click', () => {
            if (!this.isLoading) {
                this.toggleCurrency();
            }
        });
        minPriceInput.addEventListener('input', () => this.updateConversionHint());
        maxPriceInput.addEventListener('input', () => this.updateConversionHint());
        // Intercept form submission to convert USD to NGN
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
    toggleCurrency() {
        this.isLoading = true;
        const toggleBtn = document.getElementById('currencyToggle');
        toggleBtn.classList.add('loading');
        setTimeout(() => {
            this.currentCurrency = this.currentCurrency === 'NGN' ? 'USD' : 'NGN';
            this.updateUI();
            this.convertAllPrices();
            this.convertFilterInputs();
            this.isLoading = false;
            toggleBtn.classList.remove('loading');
        }, 500);
    }
    updateUI() {
        const currencyDisplay = document.getElementById('currentCurrency');
        const priceRangeCurrency = document.getElementById('priceRangeCurrency');
        const currencyInfoText = document.getElementById('currencyInfoText');
        const priceRangeDisplay = document.getElementById('priceRangeDisplay');
        if (this.currentCurrency === 'NGN') {
            currencyDisplay.textContent = '₦ NGN';
            priceRangeCurrency.textContent = '₦';
            currencyInfoText.textContent = 'Filtering in Nigerian Naira (₦)';
        } else {
            currencyDisplay.textContent = '$ USD';
            priceRangeCurrency.textContent = '$';
            currencyInfoText.textContent = 'Filtering in US Dollars ($)';
        }
        // Update price range display
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
        const timeStr = this.lastUpdated ? 
            `(Updated: ${this.lastUpdated.toLocaleTimeString()})` : '(Using default rate)';
        exchangeRateInfo.textContent = `Exchange rate: ₦${this.exchangeRate.toLocaleString()} = $1 USD ${timeStr}`;
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
        if (minPriceInput.value) {
            const currentValue = parseFloat(minPriceInput.value.replace(/,/g, ''));
            if (!isNaN(currentValue)) {
                if (this.currentCurrency === 'USD') {
                    minPriceInput.value = Math.round(currentValue / this.exchangeRate);
                } else {
                    minPriceInput.value = Math.round(currentValue * this.exchangeRate);
                }
            }
        }
        if (maxPriceInput.value) {
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
        const minPrice = document.getElementById('minPriceInput').value;
        const maxPrice = document.getElementById('maxPriceInput').value;
        const hintElement = document.getElementById('priceConversionHint');
        const hintText = document.getElementById('conversionHintText');
        if (minPrice || maxPrice) {
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
        } else {
            hintElement.classList.add('hidden');
        }
    }
}

// Initialize currency converter
const currencyConverter = new CurrencyConverter();

// Filter sidebar functionality (Mobile & Desktop)
const mobileMenuBtn = document.getElementById('mobileMenuBtn'); // Hamburger in header
const closeMobileMenu = document.getElementById('closeMobileMenu'); // X button in sidebar
const toggleFilterBtn = document.getElementById('toggleFilterBtn'); // Filter toggle button in main content
const filterSidebar = document.getElementById('filterSidebar');
const mobileFilterOverlay = document.getElementById('mobileFilterOverlay');

// Start with sidebar hidden on all devices
let filterSidebarVisible = false;

// Initialize sidebar as hidden on page load
if (filterSidebar) {
    filterSidebar.classList.add('hidden');
}

// Show toggle button on page load
if (toggleFilterBtn) {
    toggleFilterBtn.classList.remove('hidden');
}

function openFilter() {
    filterSidebar.classList.remove('hidden');
    filterSidebarVisible = true;

    if (window.innerWidth < 1024) {
        // Mobile: show overlay
        filterSidebar.classList.add('open');
        mobileFilterOverlay.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }

    if (toggleFilterBtn) toggleFilterBtn.classList.add('hidden');
}

function closeFilter() {
    // Close sidebar on all devices
    filterSidebar.classList.remove('open');
    filterSidebar.classList.add('hidden');
    filterSidebarVisible = false;

    // Mobile-specific cleanup
    if (window.innerWidth < 1024) {
        mobileFilterOverlay.classList.add('hidden');
        document.body.style.overflow = '';
    }

    // Show toggle button
    if (toggleFilterBtn) toggleFilterBtn.classList.remove('hidden');
}

// Event listeners
if (mobileMenuBtn) mobileMenuBtn.addEventListener('click', openFilter);
if (closeMobileMenu) closeMobileMenu.addEventListener('click', closeFilter);
if (toggleFilterBtn) toggleFilterBtn.addEventListener('click', openFilter);
if (mobileFilterOverlay) mobileFilterOverlay.addEventListener('click', closeFilter);

window.addEventListener('resize', function() {
    if (window.innerWidth >= 1024) {
        // Desktop: remove mobile overlay
        filterSidebar.classList.remove('open');
        mobileFilterOverlay.classList.add('hidden');
        document.body.style.overflow = '';
    }

    // Maintain toggle button visibility based on sidebar state
    if (filterSidebarVisible) {
        if (toggleFilterBtn) toggleFilterBtn.classList.add('hidden');
    } else {
        if (toggleFilterBtn) toggleFilterBtn.classList.remove('hidden');
    }
});

// Property image gallery functionality
function changePropertyImage(propertyId, direction) {
    const images = propertyImagesData[propertyId];
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

// Property selection for sharing
const propertyCheckboxes = document.querySelectorAll('.property-checkbox');
const createShareBtn = document.getElementById('createShareBtn');
const compareSelectedBtn = document.getElementById('compareSelectedBtn');
const navbarCompareBtn = document.getElementById('navbarCompareBtn');
const shareListName = document.getElementById('shareListName');
const shareDuration = document.getElementById('shareDuration');
const syncAirtableBtn = document.getElementById('syncAirtableBtn');
function updateSelectionButtons() {
    const selectedProperties = Array.from(propertyCheckboxes)
        .filter(checkbox => checkbox.checked)
        .map(checkbox => checkbox.value);
    const count = selectedProperties.length;
    document.querySelectorAll('.selected-count').forEach(span => {
        span.textContent = count;
    });
    document.querySelectorAll('.navbar-selected-count').forEach(span => {
        span.textContent = count;
    });
    if (createShareBtn) createShareBtn.disabled = count === 0 || !shareListName.value.trim();
    if (compareSelectedBtn) compareSelectedBtn.disabled = count < 2;
    if (navbarCompareBtn) navbarCompareBtn.disabled = count < 2;
}
propertyCheckboxes.forEach(checkbox => {
    checkbox.addEventListener('change', updateSelectionButtons);
});
if (shareListName) shareListName.addEventListener('input', updateSelectionButtons);

// Enhanced Property modal functionality with currency support
let currentModalImageIndex = 0;
let currentModalImages = [];
async function showPropertyModal(propertyId) {
    const modal = document.getElementById('propertyModal');
    const modalTitle = document.getElementById('modalTitle');
    const modalContent = document.getElementById('modalContent');
    // Show loading state
    modalContent.innerHTML = `
        <div class="flex items-center justify-center py-12">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            <span class="ml-3 text-gray-600">Loading property details...</span>
        </div>
    `;
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    try {
        const response = await fetch(`${URLS.propertyDetail}${propertyId}/`);
        if (!response.ok) throw new Error('Failed to fetch property details');
        const property = await response.json();
        // Set modal images
        currentModalImages = property.images || [];
        currentModalImageIndex = 0;
        // Populate modal with enhanced content and currency conversion
        modalTitle.innerHTML = `
            <i class="fas fa-home"></i>
            <span>${property.name || 'Property Details'}</span>
        `;
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
                        <div class="w-full h-64 bg-gray-100 flex items-center justify-center rounded-12">
                            <div class="text-center">
                                <i class="fas fa-image text-gray-400 text-4xl mb-2"></i>
                                <p class="text-gray-500">No images available</p>
                            </div>
                        </div>
                    `}
                </div>
                <!-- Property Information -->
                <div class="modal-section">
                    <h3 class="modal-section-title">
                        <i class="fas fa-info-circle text-blue-600"></i>
                        Property Information
                    </h3>
                    <div class="modal-info-grid">
                        <div class="modal-info-item">
                            <div class="modal-info-label">Address</div>
                            <div class="modal-info-value">${property.address || 'Not specified'}</div>
                        </div>
                        
                        <div class="modal-info-item">
                            <div class="modal-info-label">Luxury Status</div>
                            <div class="modal-info-value">
                                ${property.luxury_status === 'luxurious' ? 
                                    '<span class="text-amber-600"><i class="fas fa-crown mr-1"></i>Luxurious</span>' : 
                                    'Standard'
                                }
                            </div>
                        </div>
                        <div class="modal-info-item">
                            <div class="modal-info-label">Completion Date</div>
                            <div class="modal-info-value">${property.completion_date || 'Not specified'}</div>
                        </div>
                    </div>
                </div>
                
                <!-- Description -->
                ${property.description ? `
                    <div class="modal-section">
                        <h3 class="modal-section-title">
                            <i class="fas fa-align-left text-blue-600"></i>
                            Description
                        </h3>
                        <div class="bg-gray-50 p-4 rounded-12 border-l-4 border-blue-600">
                            <p class="text-gray-700 leading-relaxed">${property.description}</p>
                        </div>
                    </div>
                ` : ''}
               <!-- Configurations with Currency -->
            ${property.configurations?.length > 0 ? `
                <div class="modal-section">
                    <h3 class="modal-section-title">
                        <i class="fas fa-bed text-blue-600"></i>
                        Available Configurations
                    </h3>
                    <div class="space-y-3">
                        ${property.configurations.map(config => {
                            let priceDisplay = 'Price on request';
                            if (config.price && config.price !== 'TBD') {
                                // Clean the price string by removing '₦' and commas
                                const cleanPrice = parseFloat(config.price.replace('₦', '').replace(/,/g, ''));
                                if (!isNaN(cleanPrice)) {
                                    const nairaPrice = cleanPrice;
                                    if (currencyConverter.currentCurrency === 'USD') {
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
                                <div class="config-card">
                                    <div class="flex justify-between items-center mb-2">
                                        <div class="flex items-center gap-4">
                                            <span class="flex items-center gap-1 text-gray-700">
                                                <i class="fas fa-bed"></i>
                                                <strong>${config.bedrooms || 'N/A'}</strong> Bed${(config.bedrooms && config.bedrooms !== 1) ? 's' : ''}
                                            </span>
                                            <span class="flex items-center gap-1 text-gray-700">
                                                <i class="fas fa-bath"></i>
                                                <strong>${config.bathrooms || 'N/A'}</strong> Bath${(config.bathrooms && config.bathrooms !== 1) ? 's' : ''}
                                            </span>
                                            <span class="flex items-center gap-1 text-gray-700">
                                                <strong>${config.square_footage || 'N/A'} sq ft</strong> 
                                            </span>

                                        </div>
                                        <div class="text-right">
                                            <div class="text-lg font-bold text-green-600">
                                                ${priceDisplay}
                                            </div>
                                        </div>
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
                            <i class="fas fa-star text-blue-600"></i>
                            Amenities & Features
                        </h3>
                        <div class="flex flex-wrap gap-2">
                            ${property.amenities.map(amenity => `
                                <span class="amenity-tag">${amenity}</span>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}

                <!-- Progress Updates (Only for users with exact location access) -->
                ${property.progress_updates?.length > 0 ? `
                    <div class="modal-section">
                        <h3 class="modal-section-title">
                            <i class="fas fa-hard-hat text-blue-600"></i>
                            Construction Progress
                        </h3>
                        <div class="space-y-4">
                            ${property.progress_updates.map((update, index) => `
                                <div class="bg-white border ${update.is_latest ? 'border-green-500' : 'border-gray-200'} rounded-12 p-4 ${update.is_latest ? 'shadow-lg' : 'shadow-sm'}">
                                    ${update.is_latest ? `
                                        <div class="flex items-center gap-2 mb-2">
                                            <span class="bg-green-100 text-green-800 text-xs font-semibold px-3 py-1 rounded-full">
                                                <i class="fas fa-check-circle mr-1"></i>Latest Update
                                            </span>
                                        </div>
                                    ` : ''}
                                    <div class="flex justify-between items-start mb-3">
                                        <div>
                                            <h4 class="font-semibold text-lg text-gray-800">${update.stage}</h4>
                                            <p class="text-sm text-gray-500">
                                                <i class="far fa-calendar mr-1"></i>${new Date(update.update_date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
                                            </p>
                                        </div>
                                        <div class="text-right">
                                            <div class="text-2xl font-bold text-blue-600">${update.progress_percentage}%</div>
                                            <p class="text-xs text-gray-500">Complete</p>
                                        </div>
                                    </div>

                                    <!-- Progress Bar -->
                                    <div class="w-full bg-gray-200 rounded-full h-2.5 mb-3">
                                        <div class="bg-blue-600 h-2.5 rounded-full transition-all duration-500" style="width: ${update.progress_percentage}%"></div>
                                    </div>

                                    ${update.description ? `
                                        <p class="text-gray-700 text-sm mb-3 leading-relaxed">${update.description}</p>
                                    ` : ''}

                                    ${update.uploaded_by ? `
                                        <p class="text-xs text-gray-500">
                                            <i class="fas fa-user-circle mr-1"></i>Updated by ${update.uploaded_by}
                                        </p>
                                    ` : ''}

                                    <!-- Progress Images -->
                                    ${update.images?.length > 0 ? `
                                        <div class="mt-4">
                                            <p class="text-sm font-semibold text-gray-700 mb-2">
                                                <i class="fas fa-images mr-1"></i>Progress Photos (${update.images.length})
                                            </p>
                                            <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                                                ${update.images.slice(0, 4).map((img, imgIndex) => `
                                                    <div class="relative group cursor-pointer" onclick="openProgressImageGallery(${index}, ${imgIndex})">
                                                        <img src="${img}"
                                                             alt="Progress ${imgIndex + 1}"
                                                             class="w-full h-24 object-cover rounded-lg transition-transform group-hover:scale-105"
                                                             loading="lazy">
                                                        ${imgIndex === 3 && update.images.length > 4 ? `
                                                            <div class="absolute inset-0 bg-black bg-opacity-60 rounded-lg flex items-center justify-center text-white font-bold">
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

                <!-- Contact Section -->
                <div class="modal-section">
                    <h3 class="modal-section-title">
                        <i class="fas fa-phone text-blue-600"></i>
                        Contact Information
                    </h3>
                    <div class="bg-gradient-to-r from-green-50 to-green-100 p-6 rounded-12 border border-green-200">
                        <div class="text-center mb-4">
                            <p class="text-gray-700 mb-4">Interested in this property? Get in touch with us!</p>
                            <a href="https://wa.me/${property.contact?.split(' - ')[1] || '2348000000000'}?text=Hi! I'm interested in ${property.name}"
                               class="inline-flex items-center gap-2 bg-gradient-to-r from-green-500 to-green-600 text-white px-6 py-3 rounded-12 font-semibold hover:from-green-600 hover:to-green-700 transition-all transform hover:scale-105 shadow-lg"
                               target="_blank">
                                <i class="fab fa-whatsapp text-lg"></i>
                                Contact via WhatsApp
                            </a>
                        </div>
                        <div class="text-center text-sm text-gray-600">
                            <i class="fas fa-clock mr-1"></i>
                            We typically respond within minutes
                        </div>
                    </div>
                </div>
            </div>
        `;
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    } catch (error) {
        console.error('Error fetching property details:', error);
        modalContent.innerHTML = `
            <div class="text-center py-12">
                <div class="bg-red-50 border border-red-200 rounded-12 p-6">
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
function closePropertyModal() {
    const modal = document.getElementById('propertyModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';
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
document.getElementById('propertyModal').addEventListener('click', function(e) {
    if (e.target === this) {
        closePropertyModal();
    }
});
// Keyboard navigation for modal
document.addEventListener('keydown', function(e) {
    const modal = document.getElementById('propertyModal');
    if (!modal.classList.contains('hidden')) {
        if (e.key === 'Escape') {
            closePropertyModal();
        } else if (e.key === 'ArrowLeft') {
            changeModalImage(-1);
        } else if (e.key === 'ArrowRight') {
            changeModalImage(1);
        }
    }
});
// Share link functionality
if (createShareBtn) {
    createShareBtn.addEventListener('click', async () => {
        const selectedProperties = Array.from(propertyCheckboxes)
            .filter(checkbox => checkbox.checked)
            .map(checkbox => checkbox.value);
        const listName = shareListName.value.trim();
        const duration = shareDuration.value;
        if (selectedProperties.length === 0 || !listName) return;
        try {
            const response = await fetch(URLS.createSharedList, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                body: JSON.stringify({
                    name: listName,
                    property_ids: selectedProperties,
                    duration_hours: parseInt(duration)
                })
            });
            const result = await response.json();
            const shareModalContent = document.getElementById('shareModalContent');
            shareModalContent.innerHTML = `
                <div class="space-y-4">
                    <p class="text-gray-600">Your shareable link has been created successfully!</p>
                    <div class="bg-gray-100 p-3 rounded-lg">
                        <input 
                            type="text" 
                            value="${result.share_url}" 
                            id="shareLinkInput"
                            class="w-full bg-transparent border-none focus:outline-none text-gray-700"
                            readonly
                        >
                    </div>
                    <button 
                        onclick="copyShareLink()"
                        class="btn-primary w-full text-white py-2 px-4 rounded-lg font-semibold"
                    >
                        <i class="fas fa-copy mr-2"></i>Copy Link
                    </button>
                </div>
            `;
            document.getElementById('shareLinkModal').classList.remove('hidden');
            document.body.style.overflow = 'hidden';
            // Reset selection
            propertyCheckboxes.forEach(checkbox => checkbox.checked = false);
            shareListName.value = '';
            updateSelectionButtons();
        } catch (error) {
            console.error('Error creating share link:', error);
            alert('Error creating share link. Please try again.');
        }
    });
}
function copyShareLink() {
    const shareLinkInput = document.getElementById('shareLinkInput');
    shareLinkInput.select();
    document.execCommand('copy');
    alert('Link copied to clipboard!');
}
function closeShareModal() {
    const shareModal = document.getElementById('shareLinkModal');
    shareModal.classList.add('hidden');
    document.body.style.overflow = '';
}
// Sync Airtable functionality
if (syncAirtableBtn) {
    syncAirtableBtn.addEventListener('click', async () => {
        const syncStatus = document.getElementById('syncStatus');
        syncStatus.textContent = 'Syncing with Airtable...';
        syncAirtableBtn.disabled = true;
        try {
            const response = await fetch(URLS.syncAirtable, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CSRF_TOKEN
                },
                body: JSON.stringify({})
            });
            const result = await response.json();
            console.log('Sync Response:', result);
            if (result.success) {
                syncStatus.textContent = 'Sync completed successfully! Reloading page...';
                setTimeout(() => {
                    window.location.reload(); // Refresh to show new properties
                }, 2000);
            } else {
                throw new Error(result.error || 'Sync failed');
            }
        } catch (error) {
            console.error('Error syncing Airtable:', error);
            syncStatus.textContent = `Error: ${error.message}`;
            syncAirtableBtn.disabled = false;
        }
    });
}
// PDF download functionality
async function downloadPropertyPDF(propertyId) {
    try {
        //const response = await fetch(`${URLS.propertyPdf}${propertyId}/`)
        const response = await fetch(`property/${propertyId}/pdf/`);
        if (!response.ok) {
            throw new Error('Failed to generate PDF');
        }
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = `property-${propertyId}-details.pdf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
    } catch (error) {
        alert('Error downloading PDF: ' + error.message);
    }
}
// Comparison functionality
if (compareSelectedBtn) {
    compareSelectedBtn.addEventListener('click', compareSelected);
}
if (navbarCompareBtn) {
    navbarCompareBtn.addEventListener('click', compareSelected);
}
async function compareSelected() {
    const selectedProperties = Array.from(propertyCheckboxes)
        .filter(checkbox => checkbox.checked)
        .map(checkbox => checkbox.value);
    if (selectedProperties.length < 2) return;
    const modal = document.getElementById('comparisonModal');
    const content = document.getElementById('comparisonContent');
    content.innerHTML = `
        <div class="flex items-center justify-center py-12">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            <span class="ml-3 text-gray-600">Loading comparison...</span>
        </div>
    `;
    modal.classList.remove('hidden');
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
        console.log(response.status)
        if (!response.ok) throw new Error('Failed to fetch comparison data');
        const data = await response.json();
        if (!data.success) throw new Error(data.error);
        content.innerHTML = buildComparisonTable(data.properties);
        const pdfLink = document.getElementById('downloadComparisonPdf');
        pdfLink.href = data.comparison_url;
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
        }).join('<br>') || 'N/A' },
        
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
function closeComparisonModal() {
    const modal = document.getElementById('comparisonModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';
}
document.getElementById('comparisonModal').addEventListener('click', function(e) {
    if (e.target === this) {
        closeComparisonModal();
    }
});
document.addEventListener('keydown', function(e) {
    const modal = document.getElementById('comparisonModal');
    if (!modal.classList.contains('hidden') && e.key === 'Escape') {
        closeComparisonModal();
    }
});

// Sqft Slider Functionality
(function () {
    const minRange = document.getElementById('sqft-min-range');
    const maxRange = document.getElementById('sqft-max-range');
    const minHidden = document.getElementById('min_square_footage');
    const maxHidden = document.getElementById('max_square_footage');
    const minReadout = document.getElementById('sqft-min-readout');
    const maxReadout = document.getElementById('sqft-max-readout');
    const rangeFill = document.querySelector('#sqft-filter .sqft-slider__range');

    const minGap = parseInt(minRange.step || '5', 10); // keep handles from crossing

    function clampHandles() {
    let minVal = parseInt(minRange.value, 10);
    let maxVal = parseInt(maxRange.value, 10);

    if (maxVal - minVal < minGap) {
        // Push the one that was moved
        if (document.activeElement === minRange) {
        minVal = maxVal - minGap;
        minRange.value = minVal;
        } else {
        maxVal = minVal + minGap;
        maxRange.value = maxVal;
        }
    }
    updateUI();
    }

    function updateUI() {
    const min = parseInt(minRange.min, 10);
    const max = parseInt(maxRange.max, 10);
    const minVal = parseInt(minRange.value, 10);
    const maxVal = parseInt(maxRange.value, 10);

    // Update readouts and hidden fields
    minReadout.textContent = minVal.toLocaleString();
    maxReadout.textContent = maxVal.toLocaleString();
    minHidden.value = minVal;
    maxHidden.value = maxVal;

    // Update the fill between handles
    const percentMin = ((minVal - min) / (max - min)) * 100;
    const percentMax = ((maxVal - min) / (max - min)) * 100;
    rangeFill.style.left = percentMin + '%';
    rangeFill.style.right = (100 - percentMax) + '%';
    }

    // Initialize from hidden inputs (server-provided values), if present
    function initFromHidden() {
    const minProvided = parseInt(minHidden.value || minRange.min, 10);
    const maxProvided = parseInt(maxHidden.value || maxRange.max, 10);
    minRange.value = isNaN(minProvided) ? minRange.min : minProvided;
    maxRange.value = isNaN(maxProvided) ? maxRange.max : maxProvided;
    updateUI();
    }

    if (minRange) minRange.addEventListener('input', clampHandles);
    if (maxRange) maxRange.addEventListener('input', clampHandles);

    // On first paint
    if (minRange && maxRange) initFromHidden();
})();

// Progress Image Gallery Function
function openProgressImageGallery(_updateIndex, imageIndex) {
    // Get the property data from the last fetched property in the modal
    const modalContent = document.getElementById('modalContent');
    if (!modalContent) return;

    // For now, just open the image in a new tab
    // You can enhance this later with a full gallery modal
    const imgElements = modalContent.querySelectorAll('.grid img');
    if (imgElements && imgElements[imageIndex]) {
        window.open(imgElements[imageIndex].src, '_blank');
    }
}