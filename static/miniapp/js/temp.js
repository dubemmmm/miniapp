// Property Data from Django - these will be set by the template
// const properties = {{ properties_json|safe }};
// const filterRanges = {{ filter_ranges_json|safe }};
// const isFavoritesPage = {{ is_favorites_page|default:False|yesno:"true,false" }};

console.log('Properties loaded:', properties.length);
console.log('Filter ranges:', filterRanges);

const favoritePropertyIds = new Set(
    properties.filter(prop => prop.is_favorite).map(prop => prop.id)
);
window.ChatWidgetConfig = window.ChatWidgetConfig || {};
window.ChatWidgetConfig.webhook = window.ChatWidgetConfig.webhook || {};
// window.ChatWidgetConfig.webhook.url will be set by template

const getCookie = (name) => {
    if (!document.cookie) return null;
    const cookie = document.cookie.split('; ').find(row => row.startsWith(`${name}=`));
    return cookie ? decodeURIComponent(cookie.split('=')[1]) : null;
};

const getCsrfToken = () => getCookie('csrftoken');

const favoriteEndpoint = (propertyId) => `/api/properties/${propertyId}/favorite/`;

const getHeartIcon = (isActive) => isActive
    ? `<svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5A4.5 4.5 0 016.5 4 5.38 5.38 0 0112 6.09 5.38 5.38 0 0117.5 4 4.5 4.5 0 0122 8.5c0 3.78-3.4 6.86-8.55 11.54z"/></svg>`
    : `<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5A4.5 4.5 0 016.5 4 5.38 5.38 0 0112 6.09 5.38 5.38 0 0117.5 4 4.5 4.5 0 0122 8.5c0 3.78-3.4 6.86-8.55 11.54z"/></svg>`;

const favoriteButtonTemplate = (property) => `
    <button
        type="button"
        class="favorite-toggle heart-btn-v2 ${property.is_favorite ? 'saved' : ''}"
        data-property-id="${property.id}"
        aria-pressed="${property.is_favorite}"
        aria-label="${property.is_favorite ? 'Remove from favourites' : 'Save to favourites'}"
    >
        ${getHeartIcon(property.is_favorite)}
    </button>
`;

const updateFavoriteButtonVisual = (button, isFavorite) => {
    if (!button) return;
    button.setAttribute('aria-pressed', isFavorite);
    button.setAttribute('aria-label', isFavorite ? 'Remove from favourites' : 'Save to favourites');
    button.innerHTML = getHeartIcon(isFavorite);
    button.classList.toggle('saved', isFavorite);
};

const applyFavoriteState = (propertyId, isFavorite) => {
    if (isFavorite) {
        favoritePropertyIds.add(propertyId);
    } else {
        favoritePropertyIds.delete(propertyId);
    }
    const property = properties.find(prop => prop.id === propertyId);
    if (property) {
        property.is_favorite = isFavorite;
    }
};

// Currency conversion rate (fetched dynamically with fallback)
let nairaToUsdRate = 0.0012; // Fallback rate if API fails
let lastExchangeRateUpdate = null;
let currentCurrency = 'NGN'; // Default to Naira

const EXCHANGE_RATE_ENDPOINT = 'https://api.exchangerate-api.com/v4/latest/USD';

const fetchExchangeRate = async () => {
    try {
        const response = await fetch(EXCHANGE_RATE_ENDPOINT);
        if (!response.ok) {
            throw new Error(`Exchange rate request failed with status ${response.status}`);
        }
        const data = await response.json();
        const usdToNgnRate = data?.rates?.NGN;
        if (usdToNgnRate) {
            nairaToUsdRate = 1 / usdToNgnRate;
            lastExchangeRateUpdate = new Date();
            console.log(`Exchange rate updated. 1 NGN = ${nairaToUsdRate.toFixed(6)} USD (updated ${lastExchangeRateUpdate.toISOString()})`);
        } else {
            console.warn('NGN rate missing from exchange rate API response. Retaining previous rate.');
        }
    } catch (error) {
        console.error('Failed to fetch exchange rate. Using fallback rate:', nairaToUsdRate, error);
    }
};

// Fetch the latest exchange rate on load
fetchExchangeRate();

// Filter state
const filters = {
    search: '',
    bedrooms: 'all',
    completionQuarter: 'all',
    completionYear: 'all',
    luxury: 'all',
    priceRange: [filterRanges.min_price, filterRanges.max_price],
    sqftRange: [filterRanges.min_sqft || 0, filterRanges.max_sqft || 10000],
    sortBy: 'featured'
};

let selectedProperty = null;
let carouselIndex = 0;
let filtersVisible = true;
let selectedForComparison = new Set(); // Track properties selected for comparison
let locationViewState = { active: false, location: null, propertyIds: [] };

const formatCurrency = (value) => {
    if (!value || value === 0) {
        return "Price on Request";
    }
    if (currentCurrency === 'USD') {
        const usdValue = value * nairaToUsdRate;
        return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(usdValue);
    } else {
        return new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN", maximumFractionDigits: 0 }).format(value);
    }
};
const formatNumber = (value) => value.toLocaleString("en-US");

const toggleCurrency = async () => {
    if (currentCurrency === 'NGN') {
        await fetchExchangeRate();
    }
    currentCurrency = currentCurrency === 'NGN' ? 'USD' : 'NGN';
    document.getElementById('currencyLabel').textContent = currentCurrency === 'NGN' ? 'Switch to USD' : 'Switch to NGN';
    renderCards();
    // Update price range label
    updatePriceLabel();
    // Update location view grid if user is viewing a single location
    renderActiveLocationView();
    // Update modal if open
    if (selectedProperty) {
        const minConfig = selectedProperty.configurations.reduce((min, c) => c.price < min.price ? c : min);
        document.getElementById("modalPrice").textContent = formatCurrency(minConfig.price);
        // Update configurations in modal
        document.getElementById("modalConfigurations").innerHTML = selectedProperty.configurations.map(config => `
            <div class="rounded-xl sm:rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-white p-3 sm:p-4 shadow-sm">
                <div class="flex justify-between items-start gap-2">
                    <div class="flex-1 min-w-0">
                        <p class="font-semibold text-slate-900 text-sm sm:text-base truncate">${config.type}</p>
                        <p class="text-xs sm:text-sm text-slate-600 mt-1">${config.bedrooms} bed " ${config.bathrooms} bath " ${formatNumber(config.square_footage)} sqft</p>
                    </div>
                    <div class="text-right flex-shrink-0">
                        <p class="text-base sm:text-lg font-semibold text-rose-500">${formatCurrency(config.price)}</p>
                <span class="status-v2 ${config.is_available ? 'available' : 'sold'}" style="padding:3px 8px;margin-top:4px;"><span class="dot"></span>${config.is_available ? 'Available' : 'Sold out'}</span>
                    </div>
                </div>
            </div>
        `).join('');
    }
};

const statusStyles = {
    completed: "bg-emerald-100 border border-emerald-200 text-emerald-700",
    in_progress: "bg-amber-100 border border-amber-200 text-amber-700"
};

const badgePalette = {
    luxurious: "from-rose-500/90 via-rose-400/80 to-fuchsia-500/70",
    non_luxurious: "from-sky-500/80 via-sky-400/70 to-cyan-400/70"
};

const updateActiveFilterCount = () => {
    let count = 0;
    if (filters.search) count++;
    if (filters.bedrooms !== 'all') count++;
    if (filters.completionQuarter !== 'all') count++;
    if (filters.completionYear !== 'all') count++;
    if (filters.luxury !== 'all') count++;
    // Only count price filter if it's different from the initial range
    if (filters.priceRange[0] !== filterRanges.min_price || filters.priceRange[1] !== filterRanges.max_price) count++;
    // Only count sqft filter if it's different from the initial range
    if (filters.sqftRange[0] !== (filterRanges.min_sqft || 0) || filters.sqftRange[1] !== (filterRanges.max_sqft || 10000)) count++;

    const badge = document.getElementById('activeFilterCount');
    if (count > 0) {
        badge.textContent = count;
        badge.classList.remove('hidden');
        badge.classList.add('flex');
    } else {
        badge.classList.add('hidden');
        badge.classList.remove('flex');
    }
};

const toggleFilterBar = () => {
    filtersVisible = !filtersVisible;
    const content = document.getElementById('filterContent');
    const icon = document.getElementById('toggleFiltersIcon');
    const text = document.getElementById('toggleFiltersText');

    if (filtersVisible) {
        content.style.maxHeight = content.scrollHeight + 'px';
        content.style.opacity = '1';
        icon.style.transform = 'rotate(0deg)';
        text.textContent = 'Hide';
    } else {
        content.style.maxHeight = '0';
        content.style.opacity = '0';
        icon.style.transform = 'rotate(180deg)';
        text.textContent = 'Show';
    }
};

const updateStats = (properties) => {
    // Update stats if elements exist (optional feature)
    const statTotal = document.getElementById("statTotal");
    if (statTotal) statTotal.textContent = properties.length;

    const statValue = document.getElementById("statValue");
    if (statValue) {
        const totalValue = properties.reduce((sum, p) => sum + Math.min(...p.configurations.map(c => c.price)), 0);
        statValue.textContent = formatCurrency(totalValue);
    }

    const statLuxury = document.getElementById("statLuxury");
    if (statLuxury) {
        const luxuryCount = properties.filter(p => p.luxury_status === 'luxurious').length;
        statLuxury.textContent = luxuryCount;
    }

    const statCompleted = document.getElementById("statCompleted");
    if (statCompleted) {
        const completedCount = properties.filter(p => new Date(p.completion_date) <= new Date()).length;
        statCompleted.textContent = completedCount;
    }
};

const getFilteredProperties = () => {
    const normalizedSearch = filters.search.toLowerCase().trim();

    // Debug: Track filtered out properties
    const filteredOut = [];

    let filtered = properties.filter((property) => {
        const matchesSearch = normalizedSearch ?
            `${property.name} ${property.address}`.toLowerCase().includes(normalizedSearch) : true;

        const matchesBedrooms = filters.bedrooms === 'all' ||
            property.configurations.some(c => {
                if (filters.bedrooms === '5+') return c.bedrooms >= 5;
                return c.bedrooms === parseInt(filters.bedrooms);
            });

        const matchesCompletion = () => {
            if (!property.completion_date) return true;

            const completionDate = new Date(property.completion_date);
            const month = completionDate.getMonth() + 1; // JavaScript months are 0-indexed
            const year = completionDate.getFullYear();
            const propQuarter = Math.floor((month - 1) / 3) + 1;

            // Check quarter filter
            const matchesQuarter = filters.completionQuarter === 'all' ||
                                  parseInt(filters.completionQuarter) === propQuarter;

            // Check year filter
            const matchesYear = filters.completionYear === 'all' ||
                               parseInt(filters.completionYear) === year;

            return matchesQuarter && matchesYear;
        };

        const matchesLuxury = filters.luxury === 'all' || property.luxury_status === filters.luxury;

        const matchesPrice = property.configurations.some(c =>
            c.price === 0 || (c.price >= filters.priceRange[0] && c.price <= filters.priceRange[1])
        );

        const matchesSqft = property.configurations.some(c =>
            c.square_footage >= filters.sqftRange[0] && c.square_footage <= filters.sqftRange[1]
        );

        const passes = matchesSearch && matchesBedrooms && matchesCompletion() && matchesLuxury && matchesPrice && matchesSqft;

        // Debug: Log properties that don't pass
        if (!passes) {
            const reasons = [];
            if (!matchesSearch) reasons.push('search');
            if (!matchesBedrooms) reasons.push('bedrooms');
            if (!matchesCompletion()) reasons.push('completion');
            if (!matchesLuxury) reasons.push('luxury');
            if (!matchesPrice) reasons.push(`price (configs: ${JSON.stringify(property.configurations.map(c => c.price))} vs range: ${filters.priceRange}, note: price=0 means "Price on Request" and should pass)`);
            if (!matchesSqft) reasons.push(`sqft (configs: ${JSON.stringify(property.configurations.map(c => c.square_footage))} vs range: ${filters.sqftRange})`);

            filteredOut.push({
                id: property.id,
                name: property.name,
                reasons: reasons,
                configurations: property.configurations
            });
        }

        return passes;
    });

    // Debug: Log filtered out properties
    if (filteredOut.length > 0) {
        console.log('=== FILTERED OUT PROPERTIES ===');
        console.log(`Total properties: ${properties.length}`);
        console.log(`Filtered properties: ${filtered.length}`);
        console.log(`Filtered OUT: ${filteredOut.length}`);
        console.log('Current filters:', filters);
        filteredOut.forEach(prop => {
            console.log(`\nProperty ID ${prop.id}: "${prop.name}"`);
            console.log(`  Reasons: ${prop.reasons.join(', ')}`);
            console.log(`  Configurations:`, prop.configurations);
        });
        console.log('================================');
    }

    // Apply sorting
    switch (filters.sortBy) {
        case 'price-asc':
            filtered.sort((a, b) => {
                const minA = Math.min(...a.configurations.map(c => c.price || Number.MAX_SAFE_INTEGER));
                const minB = Math.min(...b.configurations.map(c => c.price || Number.MAX_SAFE_INTEGER));
                return minA - minB;
            });
            break;
        case 'price-desc':
            filtered.sort((a, b) => {
                const minA = Math.min(...a.configurations.map(c => c.price || Number.MAX_SAFE_INTEGER));
                const minB = Math.min(...b.configurations.map(c => c.price || Number.MAX_SAFE_INTEGER));
                return minB - minA;
            });
            break;
        case 'newest':
            filtered.sort((a, b) => new Date(b.completion_date) - new Date(a.completion_date));
            break;
    }

    return filtered;
};

const createPropertyCard = (property, isCompact = true) => {
    const minConfig = property.configurations.reduce((min, c) => c.price < min.price ? c : min);
    const maxBedrooms = Math.max(...property.configurations.map(c => c.bedrooms));
    const minBedrooms = Math.min(...property.configurations.map(c => c.bedrooms));
    const maxBathrooms = Math.max(...property.configurations.map(c => c.bathrooms));
    const avgSqft = Math.round(property.configurations.reduce((sum, c) => sum + c.square_footage, 0) / property.configurations.length);

    const isCompleted = new Date(property.completion_date) <= new Date();
    const badgeClass = badgePalette[property.luxury_status] || badgePalette.non_luxurious;
    const bedsLabel = minBedrooms === 0 ? 'Studio' : minBedrooms === maxBedrooms ? `${minBedrooms}` : `${minBedrooms}-${maxBedrooms}`;

    const card = document.createElement("article");
    const isSelected = selectedForComparison.has(property.id);

    if (isCompact) {
        // Card A style — Editorial Overlay (image fills, text over gradient)
        card.className = "card-editorial group flex-shrink-0";
        card.style.width = "220px";
        card.innerHTML = `
            <img src="${property.thumbnail}" alt="${property.name}" class="card-img" loading="lazy" />
            <div class="card-gradient"></div>
            <div class="card-top">
                ${favoriteButtonTemplate(property)}
                <div class="compare-checkbox" role="button" tabindex="0" aria-pressed="${isSelected}" aria-label="${isSelected ? 'Remove from comparison' : 'Add to comparison'}" title="${isSelected ? 'In comparison — click to remove' : 'Compare'}" style="width:32px;height:32px;border-radius:50%;background:${isSelected ? 'var(--coral)' : 'rgba(255,255,255,0.9)'};display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:${isSelected ? '0 0 0 3px rgba(255,77,93,0.35), 0 2px 8px rgba(11,16,36,0.10)' : '0 2px 8px rgba(11,16,36,0.10)'};backdrop-filter:blur(6px);" data-property-id="${property.id}">
                    ${isSelected ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3"><path d="M5 13l4 4L19 7"/></svg>' : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0B1024" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>'}
                </div>
            </div>
            ${property.luxury_status === 'luxurious' ? `<div style="position:absolute;top:18px;left:50%;transform:translateX(-50%);z-index:2;"><span class="status-v2 new"><span class="dot"></span>Luxury</span></div>` : ''}
            <div class="card-bottom">
                <div class="card-location">${property.address.split(',')[0]}</div>
                <div class="card-name">${property.name}</div>
                <div class="card-price">${formatCurrency(minConfig.price)}</div>
                <div class="card-specs">
                    <span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 9v11M22 12v8M2 16h20M6 12a2 2 0 0 1 2-2h4v6H2v-3a3 3 0 0 1 3-3"/><path d="M12 10h6a3 3 0 0 1 3 3v3H12z"/></svg> ${bedsLabel}</span>
                    <span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h16v3a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z"/><path d="M6 12V6a2 2 0 0 1 4 0M6 19l-1 2M18 19l1 2"/></svg> ${maxBathrooms}</span>
                    <span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 3 3 21M8 6l2 2M11 9l2 2M14 12l2 2M17 15l2 2"/></svg> ${formatNumber(avgSqft)} sqft</span>
                </div>
            </div>`;
    } else {
        // Card B style — Split (image top, white info below)
        card.className = "card-split group";
        card.innerHTML = `
            <div class="card-img-wrap">
                <img src="${property.thumbnail}" alt="${property.name}" class="card-img" loading="lazy" />
                <div class="card-top">
                    ${favoriteButtonTemplate(property)}
                    <div class="compare-checkbox" role="button" tabindex="0" aria-pressed="${isSelected}" aria-label="${isSelected ? 'Remove from comparison' : 'Add to comparison'}" title="${isSelected ? 'In comparison — click to remove' : 'Compare'}" style="width:32px;height:32px;border-radius:50%;background:${isSelected ? 'var(--coral)' : 'rgba(255,255,255,0.9)'};display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:${isSelected ? '0 0 0 3px rgba(255,77,93,0.35), 0 2px 8px rgba(11,16,36,0.10)' : '0 2px 8px rgba(11,16,36,0.10)'};backdrop-filter:blur(6px);" data-property-id="${property.id}">
                        ${isSelected ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3"><path d="M5 13l4 4L19 7"/></svg>' : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0B1024" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>'}
                    </div>
                </div>
                ${property.luxury_status === 'luxurious' ? `<div style="position:absolute;bottom:12px;left:12px;"><span class="status-v2 new"><span class="dot"></span>Luxury</span></div>` : ''}
            </div>
            <div class="card-info">
                <div class="card-location">${property.address.split(',')[0]}</div>
                <div class="card-name">${property.name}</div>
                <div class="card-price-row">
                    <div class="card-price">${formatCurrency(minConfig.price)}</div>
                    <span class="status-v2 ${isCompleted ? 'available' : 'progress'}"><span class="dot"></span>${isCompleted ? 'Available' : 'In Progress'}</span>
                </div>
                <div class="card-specs">
                    <span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 9v11M22 12v8M2 16h20M6 12a2 2 0 0 1 2-2h4v6H2v-3a3 3 0 0 1 3-3"/><path d="M12 10h6a3 3 0 0 1 3 3v3H12z"/></svg> ${bedsLabel}</span>
                    <span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h16v3a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z"/><path d="M6 12V6a2 2 0 0 1 4 0M6 19l-1 2M18 19l1 2"/></svg> ${maxBathrooms}</span>
                    <span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 3 3 21M8 6l2 2M11 9l2 2M14 12l2 2M17 15l2 2"/></svg> ${formatNumber(avgSqft)} sqft</span>
                </div>
            </div>`;
    }

    // Add event listeners
    card.addEventListener("click", (e) => {
        // Don't open modal if clicking on checkbox
        if (!e.target.closest('.compare-checkbox')) {
            openModal(property);
        }
    });

    // Handle checkbox click
    const checkbox = card.querySelector('.compare-checkbox');
    checkbox.addEventListener('click', (e) => {
        e.stopPropagation();
        togglePropertySelection(property.id);
    });
    checkbox.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            e.stopPropagation();
            togglePropertySelection(property.id);
        }
    });

    const favoriteButton = card.querySelector('.favorite-toggle');
    if (favoriteButton) {
        favoriteButton.addEventListener('click', (e) => {
            e.stopPropagation();
            handleFavoriteToggle(property.id);
        });
    }

    return card;
};

const renderCards = () => {
    const filteredProperties = getFilteredProperties();
    const locationSections = document.getElementById("locationSections");
    locationSections.innerHTML = "";

    if (!filteredProperties.length) {
        locationSections.innerHTML = `<div style="border-radius: var(--r-lg); border: 1px solid var(--slate-200); background: rgba(255,255,255,0.6); padding: 40px; text-align: center; color: var(--slate-600);">
            No properties match your filters. Try adjusting your search criteria.
        </div>`;
        updateStats([]);
        document.getElementById("portfolioCount").textContent = "0 properties";
        renderActiveLocationView();
        return;
    }

    // Group properties by location
    const byLocation = {};
    filteredProperties.forEach(prop => {
        const loc = prop.location || 'Other Locations';
        if (!byLocation[loc]) byLocation[loc] = [];
        byLocation[loc].push(prop);
    });

    // Render each location section
    Object.keys(byLocation).sort().forEach(location => {
        const locationProps = byLocation[location];
        const section = document.createElement("div");
        section.className = "space-y-4";

        const header = document.createElement("div");
        header.className = "flex items-center justify-between";
        header.style.padding = "0";
        header.style.marginBottom = "14px";
        header.innerHTML = `
            <div>
                <div class="eyebrow ink" style="font-size: 11.5px;">Properties in ${location}</div>
                <div style="font-size: 13px; color: var(--slate-500); margin-top: 2px;">${locationProps.length} ${locationProps.length === 1 ? 'listing' : 'listings'}</div>
            </div>
            <button class="view-all-btn" style="color: var(--coral); font-size: 13.5px; font-weight: 500; display: inline-flex; align-items: center; gap: 6px; cursor: pointer; background: none; border: none;" data-location="${location}">
                View all <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
            </button>
        `;

        const scrollContainer = document.createElement("div");
        scrollContainer.className = "flex gap-3 sm:gap-4 overflow-x-auto pb-4 no-scroll";
        scrollContainer.style.padding = "4px 0 4px";
        scrollContainer.style.maxWidth = "100%";

        // Show first 10 properties in horizontal scroll
        locationProps.slice(0, 10).forEach(prop => {
            const card = createPropertyCard(prop, true);
            card.classList.add("snap-start");
            scrollContainer.appendChild(card);
        });

        section.appendChild(header);
        section.appendChild(scrollContainer);
        locationSections.appendChild(section);
    });

    // Add click listeners for "View All" buttons
    document.querySelectorAll('.view-all-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const location = e.target.getAttribute('data-location');
            showLocationViewAll(location, byLocation[location]);
        });
    });

    document.getElementById("portfolioCount").textContent = `${filteredProperties.length} properties`;
    updateStats(filteredProperties);
    renderActiveLocationView();
};

const showLocationViewAll = (location, properties) => {
    locationViewState = {
        active: true,
        location,
        propertyIds: properties.map(prop => prop.id)
    };
    document.getElementById("locationSections").classList.add("hidden");
    document.getElementById("locationViewAll").classList.remove("hidden");
    document.getElementById("locationViewAllTitle").textContent = `${location} (${properties.length} properties)`;

    const grid = document.getElementById("locationViewAllGrid");
    grid.innerHTML = "";

    properties.forEach((property) => {
        const card = createPropertyCard(property, false);
        card.classList.add("fade-enter");
        grid.appendChild(card);
        requestAnimationFrame(() => card.classList.add("fade-enter-active"));
    });
};

document.getElementById("backToLocations").addEventListener("click", () => {
    document.getElementById("locationViewAll").classList.add("hidden");
    document.getElementById("locationSections").classList.remove("hidden");
    locationViewState = { active: false, location: null, propertyIds: [] };
});

const renderActiveLocationView = () => {
    if (!locationViewState.active) return;
    const activeProperties = properties.filter(prop => locationViewState.propertyIds.includes(prop.id));
    if (!activeProperties.length) {
        locationViewState = { active: false, location: null, propertyIds: [] };
        document.getElementById("locationViewAll").classList.add("hidden");
        document.getElementById("locationSections").classList.remove("hidden");
        return;
    }
    showLocationViewAll(locationViewState.location, activeProperties);
};

const handleFavoriteToggle = async (propertyId) => {
    const previousState = favoritePropertyIds.has(propertyId);
    const upcomingState = !previousState;
    const buttons = document.querySelectorAll(`.favorite-toggle[data-property-id="${propertyId}"]`);

    buttons.forEach(button => {
        button.disabled = true;
        updateFavoriteButtonVisual(button, upcomingState);
    });

    applyFavoriteState(propertyId, upcomingState);

    try {
        const response = await fetch(favoriteEndpoint(propertyId), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({}),
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to update favourite');
        }

        applyFavoriteState(propertyId, data.is_favorite);
        buttons.forEach(button => updateFavoriteButtonVisual(button, data.is_favorite));

        if (!data.is_favorite && isFavoritesPage) {
            const propertyIndex = properties.findIndex(p => p.id === propertyId);
            if (propertyIndex !== -1) {
                properties.splice(propertyIndex, 1);
            }
            if (locationViewState.propertyIds && locationViewState.propertyIds.length) {
                locationViewState.propertyIds = locationViewState.propertyIds.filter(id => id !== propertyId);
            }
            selectedForComparison.delete(propertyId);
            updateCompareButton();
        }
    } catch (error) {
        console.error('Favourite toggle failed:', error);
        applyFavoriteState(propertyId, previousState);
        buttons.forEach(button => updateFavoriteButtonVisual(button, previousState));
        alert('Could not update favourite. Please try again.');
    } finally {
        buttons.forEach(button => (button.disabled = false));
        renderCards();
    }
};

const updateCarouselDots = (images) => {
    const dots = document.getElementById("carouselDots");
    dots.innerHTML = images.map((_, index) =>
        `<span style="flex:1;height:5px;border-radius:3px;background:${index === carouselIndex ? 'white' : 'rgba(255,255,255,0.35)'};"></span>`
    ).join("");
};

const openModal = (property) => {
    selectedProperty = property;
    carouselIndex = 0;

    // Reset enquiry form state for every new property
    const panel = document.getElementById('enquiryFormPanel');
    const form = document.getElementById('enquiryForm');
    const success = document.getElementById('enquirySuccess');
    if (panel) panel.classList.add('hidden');
    if (form) { form.reset(); form.classList.remove('hidden'); }
    if (success) success.classList.add('hidden');
    document.querySelectorAll('.enq-error').forEach(el => { el.classList.add('hidden'); el.textContent = ''; });
    const genErr = document.getElementById('enqGeneralError');
    if (genErr) genErr.classList.add('hidden');
    const btn = document.getElementById('enqSubmitBtn');
    if (btn) { btn.disabled = false; btn.textContent = 'Send Enquiry'; }

    const addressParts = property.address.split(',');
    const city = addressParts[addressParts.length - 2]?.trim() || '';
    const state = addressParts[addressParts.length - 1]?.trim() || '';

    document.getElementById("modalCity").textContent = `${city}, ${state}`;
    document.getElementById("modalTitle").textContent = property.name;
    document.getElementById("modalDescription").textContent = property.description;

    const minConfig = property.configurations.reduce((min, c) => c.price < min.price ? c : min);
    document.getElementById("modalPrice").textContent = formatCurrency(minConfig.price);
    document.getElementById("modalCompletionDate").textContent = `Completion: ${new Date(property.completion_date).toLocaleDateString()}`;

    const isCompleted = new Date(property.completion_date) <= new Date();
    const statusClass = isCompleted ? statusStyles.completed : statusStyles.in_progress;
    document.getElementById("modalStatusBadge").className = `status-v2 ${isCompleted ? 'available' : 'progress'}`;
    document.getElementById("modalStatusBadge").innerHTML = `<span class="dot"></span>${isCompleted ? 'Completed' : 'In Progress'}`;

    const metaParts = [
        `<span style="display:inline-flex;align-items:center;gap:6px;"><svg width="14" height="14" viewBox="0 0 24 24" fill="rgba(255,255,255,0.85)" stroke="none"><path d="M12 22s7-6.13 7-12a7 7 0 1 0-14 0c0 5.87 7 12 7 12z"/><circle cx="12" cy="10" r="2.5" fill="white"/></svg> <span style="font-size:13px;">${property.address}</span></span>`
    ];
    if (property.contact_name) {
        metaParts.push(`<span style="display:inline-flex;align-items:center;gap:6px;"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.85)" stroke-width="1.6"><circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 12 0v1"/></svg> <span style="font-size:13px;">${property.contact_name}</span></span>`);
    }
    if (property.contact_phone) {
        metaParts.push(`<span style="display:inline-flex;align-items:center;gap:6px;"><svg width="14" height="14" viewBox="0 0 24 24" fill="rgba(255,255,255,0.85)" stroke="none"><path d="M20 15.5c-1.25 0-2.45-.2-3.57-.57a1 1 0 0 0-1.02.24l-2.2 2.2a15.05 15.05 0 0 1-6.59-6.59l2.2-2.2a1 1 0 0 0 .24-1.02A11.5 11.5 0 0 1 8.5 4a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1c0 9.39 7.61 17 17 17a1 1 0 0 0 1-1v-3.5a1 1 0 0 0-1-1z"/></svg> <span style="font-size:13px;">${property.contact_phone}</span></span>`);
    }
    document.getElementById("modalMeta").innerHTML = metaParts.join('');

    document.getElementById("modalConfigurations").innerHTML = property.configurations.map(config => `
        <div class="config-row ${config.is_available ? '' : 'sold-out'}">
            <div>
                <div style="font-weight:600;font-size:14.5px;">${config.type}</div>
                <div style="font-size:12.5px;color:var(--slate-500);font-family:var(--font-mono);margin-top:2px;">
                    ${config.bedrooms} bd · ${config.bathrooms} ba · ${formatNumber(config.square_footage)} sqft
                </div>
            </div>
            <div style="text-align:right;">
                <div style="font-weight:600;font-size:14px;color:${config.is_available ? 'var(--coral-700)' : 'var(--slate-400)'};font-variant-numeric:tabular-nums;">
                    ${formatCurrency(config.price)}</div>
                    <p class="text-[10px] sm:text-xs ${config.is_available ? 'text-emerald-600' : 'text-slate-400'}">${config.is_available ? ' Available' : 'Sold Out'}</p>
                </div>
            </div>
        </div>
    `).join('');

    document.getElementById("modalAmenities").innerHTML = property.amenities.map(amenity => `
        <div class="amenity-chip">
            <span class="amenity-icon">${amenity.icon}</span>
            <div style="flex:1;min-width:0;">
                <div style="font-weight:500;font-size:13px;">${amenity.name}</div>
                <div style="font-size:11px;color:var(--slate-500);">${amenity.description}</div>
            </div>
        </div>
    `).join('');

    // Show/hide progress section based on whether there are progress updates
    const progressSection = document.getElementById("progressSection");
    if (property.progress && property.progress.length > 0) {
        progressSection.classList.remove("hidden");
        document.getElementById("modalProgress").innerHTML = property.progress.map(progress => `
            <div style="background:white;border:1px solid var(--slate-200);border-radius:var(--r-md);padding:16px 18px;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <div style="font-weight:600;font-size:14px;">${progress.stage}</div>
                    <div style="font-family:var(--font-mono);font-size:13px;color:var(--coral);">${progress.progress_percentage}%</div>
                </div>
                <div class="progress-bar-v2" style="margin-top:10px;">
                    <div class="fill" style="width: ${progress.progress_percentage}%"></div>
                </div>
                <div style="display:flex;justify-content:space-between;margin-top:10px;font-size:12.5px;">
                    <span style="color:var(--slate-600);">${progress.description}</span>
                    <span style="color:var(--slate-400);font-family:var(--font-mono);">${new Date(progress.update_date).toLocaleDateString()}</span>
                </div>
                ${progress.images && progress.images.length > 0 ? `
                    <div class="flex gap-2 overflow-x-auto pb-2 no-scroll" style="margin-top:10px;">
                        ${progress.images.map(img => `
                            <img src="${img.image}" alt="${img.caption || 'Progress update image'}" style="height:80px;width:auto;border-radius:var(--r-sm);object-fit:cover;flex-shrink:0;border:1px solid var(--slate-200);" />
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `).join('');
    } else {
        progressSection.classList.add("hidden");
    }

    document.getElementById("carouselImage").src = property.images[carouselIndex].image;
    updateCarouselDots(property.images);

    const modal = document.getElementById("propertyModal");
    modal.classList.remove("hidden");
    modal.classList.add("flex", "modal-open");
    // Prevent body scroll when modal is open
    document.body.style.overflow = 'hidden';
};

const closeModal = () => {
    selectedProperty = null;
    const modal = document.getElementById("propertyModal");
    modal.classList.add("hidden");
    modal.classList.remove("flex", "modal-open");
    // Restore body scroll when modal is closed
    document.body.style.overflow = '';
};

const updatePriceLabel = () => {
    document.getElementById("priceRangeLabel").textContent =
        `${formatCurrency(filters.priceRange[0])} - ${formatCurrency(filters.priceRange[1])}`;
};

const updateSqftLabel = () => {
    document.getElementById("sqftRangeLabel").textContent =
        `${formatNumber(filters.sqftRange[0])} - ${formatNumber(filters.sqftRange[1])} sqft`;
};

const initFilters = () => {
    // Populate year dropdown from available years
    const yearSelect = document.getElementById("completionYearSelect");
    const availableYears = new Set();
    filterRanges.quarter_year_options.forEach(option => {
        const year = option.split(' ')[1]; // Extract year from "Q1 2027"
        availableYears.add(year);
    });
    Array.from(availableYears).sort().forEach(year => {
        const optionEl = document.createElement('option');
        optionEl.value = year;
        optionEl.textContent = year;
        yearSelect.appendChild(optionEl);
    });

    // Toggle filter bar (button + the chevron chip beside it)
    document.getElementById('toggleFilters').addEventListener('click', toggleFilterBar);
    const filtersArrow = document.getElementById('toggleFiltersArrow');
    if (filtersArrow) {
        filtersArrow.addEventListener('click', toggleFilterBar);
        filtersArrow.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggleFilterBar();
            }
        });
    }

    // Search
    document.getElementById("searchInput").addEventListener("input", (e) => {
        filters.search = e.target.value;
        updateActiveFilterCount();
        renderCards();
    });

    // Bedrooms
    document.getElementById("bedroomsSelect").addEventListener("change", (e) => {
        filters.bedrooms = e.target.value;
        updateActiveFilterCount();
        renderCards();
    });

    // Completion Quarter
    document.getElementById("completionQuarterSelect").addEventListener("change", (e) => {
        filters.completionQuarter = e.target.value;
        updateActiveFilterCount();
        renderCards();
    });

    // Completion Year
    document.getElementById("completionYearSelect").addEventListener("change", (e) => {
        filters.completionYear = e.target.value;
        updateActiveFilterCount();
        renderCards();
    });

    // Luxury
    document.getElementById("luxurySelect").addEventListener("change", (e) => {
        filters.luxury = e.target.value;
        updateActiveFilterCount();
        renderCards();
    });

    // Sort
    document.getElementById("sortSelect").addEventListener("change", (e) => {
        filters.sortBy = e.target.value;
        renderCards();
    });

    const minInput = document.getElementById("minPriceRange");
    const maxInput = document.getElementById("maxPriceRange");

    // Initialize price range sliders with dynamic values
    minInput.min = filterRanges.min_price;
    minInput.max = filterRanges.max_price;
    minInput.value = filterRanges.min_price;
    minInput.step = 100000;

    maxInput.min = filterRanges.min_price;
    maxInput.max = filterRanges.max_price;
    maxInput.value = filterRanges.max_price;
    maxInput.step = 100000;

    const updatePriceRange = () => {
        filters.priceRange = [Number(minInput.value), Number(maxInput.value)];
        if (filters.priceRange[1] - filters.priceRange[0] < 100000) {
            maxInput.value = Number(minInput.value) + 100000;
            filters.priceRange[1] = Number(maxInput.value);
        }
        updatePriceLabel();
        updateActiveFilterCount();
        renderCards();
    };

    minInput.addEventListener("input", updatePriceRange);
    maxInput.addEventListener("input", updatePriceRange);
    updatePriceLabel();

    // Initialize square footage range sliders
    const minSqftInput = document.getElementById("minSqftRange");
    const maxSqftInput = document.getElementById("maxSqftRange");

    minSqftInput.min = filterRanges.min_sqft || 0;
    minSqftInput.max = filterRanges.max_sqft || 10000;
    minSqftInput.value = filterRanges.min_sqft || 0;
    minSqftInput.step = 100;

    maxSqftInput.min = filterRanges.min_sqft || 0;
    maxSqftInput.max = filterRanges.max_sqft || 10000;
    maxSqftInput.value = filterRanges.max_sqft || 10000;
    maxSqftInput.step = 100;

    const updateSqftRange = () => {
        filters.sqftRange = [Number(minSqftInput.value), Number(maxSqftInput.value)];
        if (filters.sqftRange[1] - filters.sqftRange[0] < 100) {
            maxSqftInput.value = Number(minSqftInput.value) + 100;
            filters.sqftRange[1] = Number(maxSqftInput.value);
        }
        updateSqftLabel();
        updateActiveFilterCount();
        renderCards();
    };

    minSqftInput.addEventListener("input", updateSqftRange);
    maxSqftInput.addEventListener("input", updateSqftRange);
    updateSqftLabel();

    document.getElementById("resetFilters").addEventListener("click", () => {
        filters.search = '';
        filters.bedrooms = 'all';
        filters.completionQuarter = 'all';
        filters.completionYear = 'all';
        filters.luxury = 'all';
        filters.priceRange = [filterRanges.min_price, filterRanges.max_price];
        filters.sqftRange = [filterRanges.min_sqft || 0, filterRanges.max_sqft || 10000];

        document.getElementById("searchInput").value = '';
        document.getElementById("bedroomsSelect").value = 'all';
        document.getElementById("completionQuarterSelect").value = 'all';
        document.getElementById("completionYearSelect").value = 'all';
        document.getElementById("luxurySelect").value = 'all';
        minInput.value = filterRanges.min_price;
        maxInput.value = filterRanges.max_price;
        minSqftInput.value = filterRanges.min_sqft || 0;
        maxSqftInput.value = filterRanges.max_sqft || 10000;
        updatePriceLabel();
        updateSqftLabel();
        updateActiveFilterCount();
        renderCards();
    });

    updateActiveFilterCount();
};

document.getElementById("propertyModal").addEventListener("click", (e) => {
    if (e.target.id === "propertyModal") closeModal();
});
document.getElementById("closeModal").addEventListener("click", closeModal);

document.getElementById("brochureBtn").addEventListener("click", () => {
    if (selectedProperty) {
        // Construct the PDF download URL
        const pdfUrl = `/property/${selectedProperty.id}/pdf/`;
        console.log('Downloading brochure from:', pdfUrl);
        // Open in new tab to trigger download
        window.open(pdfUrl, '_blank');
    }
});

document.getElementById("prevImage").addEventListener("click", () => {
    if (!selectedProperty) return;
    carouselIndex = (carouselIndex - 1 + selectedProperty.images.length) % selectedProperty.images.length;
    document.getElementById("carouselImage").src = selectedProperty.images[carouselIndex].image;
    updateCarouselDots(selectedProperty.images);
});

document.getElementById("nextImage").addEventListener("click", () => {
    if (!selectedProperty) return;
    carouselIndex = (carouselIndex + 1) % selectedProperty.images.length;
    document.getElementById("carouselImage").src = selectedProperty.images[carouselIndex].image;
    updateCarouselDots(selectedProperty.images);
});

// Helper functions for WhatsApp
const extractPhoneNumber = (phoneString) => {
    // Remove all non-digit characters
    return phoneString.replace(/\D/g, '');
};

const formatWhatsAppNumber = (phoneNumber) => {
    // If number doesn't start with country code, assume Nigeria (+234)
    if (phoneNumber.startsWith('0')) {
        return '234' + phoneNumber.substring(1);
    } else if (phoneNumber.startsWith('234')) {
        return phoneNumber;
    } else if (phoneNumber.startsWith('+234')) {
        return phoneNumber.substring(1);
    }
    return phoneNumber;
};

document.getElementById("contactBtn").addEventListener("click", () => {
    const panel = document.getElementById('enquiryFormPanel');
    const success = document.getElementById('enquirySuccess');
    if (!panel) return;
    // Reset form when opening fresh (not after a successful submission)
    if (panel.classList.contains('hidden')) {
        const form = document.getElementById('enquiryForm');
        if (form && (success && success.classList.contains('hidden'))) {
            form.reset();
            document.querySelectorAll('.enq-error').forEach(el => el.classList.add('hidden'));
            const genErr = document.getElementById('enqGeneralError');
            if (genErr) genErr.classList.add('hidden');
        }
    }
    panel.classList.toggle('hidden');
});

// Enquiry form submission
document.getElementById('enquiryForm').addEventListener('submit', function(e) {
    e.preventDefault();
    if (!selectedProperty) return;

    // Clear previous errors
    document.querySelectorAll('.enq-error').forEach(el => { el.classList.add('hidden'); el.textContent = ''; });
    const genErr = document.getElementById('enqGeneralError');
    genErr.classList.add('hidden');

    const btn = document.getElementById('enqSubmitBtn');
    btn.disabled = true;
    btn.textContent = 'Sending...';

    const formData = new FormData(this);
    const csrfToken = getCsrfToken();

    fetch(`/crm/enquire/${selectedProperty.id}/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
        body: formData,
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            document.getElementById('enquiryForm').classList.add('hidden');
            document.getElementById('enquirySuccess').classList.remove('hidden');
        } else if (data.errors) {
            Object.entries(data.errors).forEach(([field, errs]) => {
                const el = document.querySelector(`.enq-error[data-field="${field}"]`);
                if (el) { el.textContent = Array.isArray(errs) ? errs[0] : errs; el.classList.remove('hidden'); }
            });
            btn.disabled = false;
            btn.textContent = 'Send Enquiry';
        } else {
            genErr.textContent = data.error || 'An error occurred. Please try again.';
            genErr.classList.remove('hidden');
            btn.disabled = false;
            btn.textContent = 'Send Enquiry';
        }
    })
    .catch(() => {
        genErr.textContent = 'Network error. Please try again.';
        genErr.classList.remove('hidden');
        btn.disabled = false;
        btn.textContent = 'Send Enquiry';
    });
});

// Property comparison functions
const togglePropertySelection = (propertyId) => {
    if (selectedForComparison.has(propertyId)) {
        selectedForComparison.delete(propertyId);
    } else {
        if (selectedForComparison.size >= 5) {
            alert('You can compare up to 5 properties at a time');
            return;
        }
        selectedForComparison.add(propertyId);
    }
    updateCompareButton();
    renderCards();
};

const updateCompareButton = () => {
    const wrapper = document.getElementById('compareButton');
    const trigger = document.getElementById('compareTrigger');
    const label = document.getElementById('compareBtnLabel');
    const n = selectedForComparison.size;

    if (n === 0) {
        wrapper.classList.add('hidden');
        return;
    }
    wrapper.classList.remove('hidden');

    if (n === 1) {
        // One picked — guide the user to the second so the feature is discoverable.
        label.textContent = 'Select 1 more to compare';
        trigger.style.background = 'white';
        trigger.style.color = 'var(--ink)';
        trigger.style.border = '1px solid var(--slate-200)';
        trigger.style.boxShadow = 'var(--shadow-lg)';
        trigger.style.cursor = 'default';
    } else {
        label.textContent = `Compare (${n})`;
        trigger.style.background = 'var(--coral)';
        trigger.style.color = 'white';
        trigger.style.border = 'none';
        trigger.style.boxShadow = 'var(--shadow-coral)';
        trigger.style.cursor = 'pointer';
    }
};

const showComparison = async () => {
    // Need at least two to compare; the button is in a hint state at one.
    if (selectedForComparison.size < 2) return;

    const propertyIds = Array.from(selectedForComparison);

    // Get property data for comparison
    const comparisonProperties = properties.filter(p => propertyIds.includes(p.id));

    // Build comparison table
    const comparisonHTML = buildComparisonTable(comparisonProperties);
    document.getElementById('comparisonContent').innerHTML = comparisonHTML;

    // Show modal
    const modal = document.getElementById('comparisonModal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.body.style.overflow = 'hidden';
};

const buildComparisonTable = (properties) => {
    if (!properties.length) return '<p class="text-slate-600">No properties selected</p>';

    return `
        <div class="overflow-x-auto">
            <table class="w-full border-collapse">
                <thead>
                    <tr class="border-b-2 border-slate-200">
                        <th class="p-3 text-left font-semibold text-slate-900 bg-slate-50 sticky left-0 z-10">Feature</th>
                        ${properties.map(p => `
                            <th class="p-3 text-left font-semibold text-slate-900">
                                <div class="min-w-[200px]">
                                    <img src="${p.thumbnail}" alt="${p.name}" class="w-full h-32 object-cover rounded-lg mb-2" />
                                    <p class="font-semibold text-sm">${p.name}</p>
                                    <p class="text-xs text-slate-500 mt-1">${p.address}</p>
                                </div>
                            </th>
                        `).join('')}
                    </tr>
                </thead>
                <tbody>
                    <tr class="border-b border-slate-100">
                        <td class="p-3 font-medium text-slate-700 bg-slate-50 sticky left-0">Price Range</td>
                        ${properties.map(p => {
                            const prices = p.configurations.map(c => c.price).filter(price => price > 0);
                            const minPrice = prices.length ? Math.min(...prices) : 0;
                            const maxPrice = prices.length ? Math.max(...prices) : 0;
                            return `<td class="p-3">${minPrice === maxPrice ? formatCurrency(minPrice) : `${formatCurrency(minPrice)} - ${formatCurrency(maxPrice)}`}</td>`;
                        }).join('')}
                    </tr>
                    <tr class="border-b border-slate-100">
                        <td class="p-3 font-medium text-slate-700 bg-slate-50 sticky left-0">Bedrooms</td>
                        ${properties.map(p => {
                            const bedrooms = [...new Set(p.configurations.map(c => c.bedrooms))].sort((a, b) => a - b);
                            return `<td class="p-3">${bedrooms.length === 1 ? bedrooms[0] : `${bedrooms[0]} - ${bedrooms[bedrooms.length - 1]}`}</td>`;
                        }).join('')}
                    </tr>
                    <tr class="border-b border-slate-100">
                        <td class="p-3 font-medium text-slate-700 bg-slate-50 sticky left-0">Bathrooms</td>
                        ${properties.map(p => {
                            const bathrooms = [...new Set(p.configurations.map(c => c.bathrooms))].sort((a, b) => a - b);
                            return `<td class="p-3">${bathrooms.length === 1 ? bathrooms[0] : `${bathrooms[0]} - ${bathrooms[bathrooms.length - 1]}`}</td>`;
                        }).join('')}
                    </tr>
                    <tr class="border-b border-slate-100">
                        <td class="p-3 font-medium text-slate-700 bg-slate-50 sticky left-0">Square Footage</td>
                        ${properties.map(p => {
                            const sqft = p.configurations.map(c => c.square_footage);
                            const minSqft = Math.min(...sqft);
                            const maxSqft = Math.max(...sqft);
                            return `<td class="p-3">${minSqft === maxSqft ? formatNumber(minSqft) : `${formatNumber(minSqft)} - ${formatNumber(maxSqft)}`} sqft</td>`;
                        }).join('')}
                    </tr>
                    <tr class="border-b border-slate-100">
                        <td class="p-3 font-medium text-slate-700 bg-slate-50 sticky left-0">Type</td>
                        ${properties.map(p => `<td class="p-3">${p.luxury_status === 'luxurious' ? '( Luxurious' : 'Standard'}</td>`).join('')}
                    </tr>
                    <tr class="border-b border-slate-100">
                        <td class="p-3 font-medium text-slate-700 bg-slate-50 sticky left-0">Location</td>
                        ${properties.map(p => `<td class="p-3">${p.location || 'N/A'}</td>`).join('')}
                    </tr>
                    <tr class="border-b border-slate-100">
                        <td class="p-3 font-medium text-slate-700 bg-slate-50 sticky left-0">Amenities</td>
                        ${properties.map(p => `
                            <td class="p-3">
                                <ul class="text-sm space-y-1">
                                    ${p.amenities.slice(0, 5).map(a => `<li> ${a.name}</li>`).join('')}
                                    ${p.amenities.length > 5 ? `<li class="text-slate-500">+ ${p.amenities.length - 5} more</li>` : ''}
                                </ul>
                            </td>
                        `).join('')}
                    </tr>
                    <tr class="border-b border-slate-100">
                        <td class="p-3 font-medium text-slate-700 bg-slate-50 sticky left-0">Completion Date</td>
                        ${properties.map(p => `<td class="p-3">${p.completion_date ? new Date(p.completion_date).toLocaleDateString() : 'N/A'}</td>`).join('')}
                    </tr>
                    <tr>
                        <td class="p-3 font-medium text-slate-700 bg-slate-50 sticky left-0">Actions</td>
                        ${properties.map(p => `
                            <td class="p-3">
                                <button onclick="openModalById(${p.id})" class="text-sm text-rose-500 hover:text-rose-600 font-medium">View Details �</button>
                            </td>
                        `).join('')}
                    </tr>
                </tbody>
            </table>
        </div>
    `;
};

const openModalById = (propertyId) => {
    const property = properties.find(p => p.id === propertyId);
    if (property) {
        closeComparisonModal();
        openModal(property);
    }
};

const closeComparisonModal = () => {
    const modal = document.getElementById('comparisonModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.body.style.overflow = '';
};

// Event listeners for comparison
document.getElementById('compareButton').addEventListener('click', showComparison);
document.getElementById('closeComparisonModal').addEventListener('click', closeComparisonModal);
document.getElementById('comparisonModal').addEventListener('click', (e) => {
    if (e.target.id === 'comparisonModal') closeComparisonModal();
});

const profileMenuButton = document.getElementById('profileMenuButton');
const profileMenu = document.getElementById('profileMenu');
if (profileMenuButton && profileMenu) {
    const closeMenu = () => {
        profileMenu.classList.add('hidden');
        profileMenuButton.setAttribute('aria-expanded', 'false');
    };
    profileMenuButton.addEventListener('click', (event) => {
        event.stopPropagation();
        const isOpen = profileMenu.classList.toggle('hidden');
        profileMenuButton.setAttribute('aria-expanded', (!isOpen).toString());
    });
    document.addEventListener('click', (event) => {
        if (!profileMenu.contains(event.target) && !profileMenuButton.contains(event.target)) {
            closeMenu();
        }
    });
    window.addEventListener('blur', closeMenu);
}

// ——— Populate hero featured card & stats ———
const populateHero = () => {
    if (!properties.length) return;

    // Stats
    const countEl = document.getElementById('heroStatCount');
    const districtsEl = document.getElementById('heroStatDistricts');
    const highestEl = document.getElementById('heroStatHighest');

    if (countEl) countEl.textContent = properties.length;

    if (districtsEl) {
        const districts = new Set(properties.map(p => p.location || '').filter(Boolean));
        districtsEl.textContent = districts.size;
    }

    if (highestEl) {
        let highest = 0;
        properties.forEach(p => {
            p.configurations.forEach(c => { if (c.price > highest) highest = c.price; });
        });
        if (highest > 0) {
            if (highest >= 1e9) highestEl.textContent = '₦' + (highest / 1e9).toFixed(1) + 'B';
            else if (highest >= 1e6) highestEl.textContent = '₦' + (highest / 1e6).toFixed(0) + 'M';
            else highestEl.textContent = formatCurrency(highest);
        }
    }

    // Featured card — pick luxury or first property
    const featured = properties.find(p => p.luxury_status === 'luxurious') || properties[0];
    const card = document.getElementById('heroFeaturedCard');
    if (!card || !featured) return;

    const minConfig = featured.configurations.reduce((min, c) => c.price < min.price ? c : min);

    card.style.background = `url(${featured.thumbnail}) center/cover, var(--slate-200)`;
    card.innerHTML = `
        <div style="position:absolute;inset:0;background:linear-gradient(180deg, rgba(11,16,36,0.10) 0%, rgba(11,16,36,0) 30%, rgba(11,16,36,0.85) 100%);"></div>
        <div style="position:absolute;top:18px;left:18px;right:18px;display:flex;justify-content:space-between;align-items:center;z-index:2;">
            <span class="status-v2 new" style="background:rgba(255,255,255,0.95);color:var(--coral-700);">
                <span class="dot"></span>Editor's pick${featured.luxury_status === 'luxurious' ? ' · Luxury' : ''}
            </span>
            ${favoriteButtonTemplate(featured)}
        </div>
        <div style="position:absolute;left:24px;right:24px;bottom:22px;color:white;z-index:2;">
            <div class="eyebrow" style="color:rgba(255,255,255,0.9);font-size:10.5px;">${featured.address.split(',')[0]}</div>
            <div class="serif-display" style="font-size:44px;margin:4px 0 6px;">
                ${featured.name.split(' ')[0]} <span class="italic-accent">${featured.name.split(' ').slice(1).join(' ')}</span>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;">
                <div style="font-weight:600;font-size:18px;font-variant-numeric:tabular-nums;">${formatCurrency(minConfig.price)}</div>
                <button class="btn-v2" style="background:white;color:var(--ink);padding:9px 16px;border:none;cursor:pointer;" onclick="event.stopPropagation();">
                    Open · <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
                </button>
            </div>
        </div>
    `;

    // Click opens modal
    card.addEventListener('click', () => openModal(featured));

    // Favorite button
    const favBtn = card.querySelector('.favorite-toggle');
    if (favBtn) {
        favBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            handleFavoriteToggle(featured.id);
        });
    }
};

populateHero();

try {
    initFilters();
    if (filtersVisible) {
        toggleFilterBar();
    }
    renderCards();
} catch (error) {
    console.error('Initialization error:', error);
    document.getElementById("locationSections").innerHTML = `
        <div style="border-radius: var(--r-lg); border: 1px solid var(--coral-100); background: var(--coral-50); padding: 40px; text-align: center; color: var(--coral-700);">
            <p style="font-weight:600;margin-bottom:8px;">Error loading properties</p>
            <p style="font-size:14px;">${error.message}</p>
            <p style="font-size:12px;margin-top:8px;color:var(--slate-500);">Check console for details</p>
        </div>`;
}
