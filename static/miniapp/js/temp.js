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
        class="favorite-toggle w-8 h-8 rounded-full flex items-center justify-center transition shadow-lg hover:scale-105 hover:text-rose-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300 ${property.is_favorite ? 'bg-rose-500/90 text-white shadow-rose-400/50' : 'bg-white/80 text-slate-500'}"
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
    button.classList.toggle('bg-rose-500/90', isFavorite);
    button.classList.toggle('text-white', isFavorite);
    button.classList.toggle('shadow-rose-400/50', isFavorite);
    button.classList.toggle('bg-white/80', !isFavorite);
    button.classList.toggle('text-slate-500', !isFavorite);
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
                        <p class="text-[10px] sm:text-xs ${config.is_available ? 'text-emerald-600' : 'text-slate-400'}">${config.is_available ? ' Available' : 'Sold Out'}</p>
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
    const statusClass = isCompleted ? statusStyles.completed : statusStyles.in_progress;
    const badgeClass = badgePalette[property.luxury_status] || badgePalette.non_luxurious;

    const card = document.createElement("article");
    card.className = isCompact
        ? "group cursor-pointer overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lg transition flex-shrink-0 w-64"
        : "group cursor-pointer overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl transition";

    const isSelected = selectedForComparison.has(property.id);

    card.innerHTML = `
        <div class="relative ${isCompact ? 'h-40' : 'h-40 sm:h-56 md:h-64'} overflow-hidden">
            <img src="${property.thumbnail}" alt="${property.name}" class="h-full w-full object-cover transition duration-700 group-hover:scale-105" loading="lazy" />
            <div class="absolute inset-0 bg-gradient-to-t from-slate-950/80 via-slate-950/10 to-transparent"></div>
            <div class="absolute left-2 top-2 flex items-center gap-1 text-xs font-medium flex-wrap">
                ${favoriteButtonTemplate(property)}
                ${property.luxury_status === 'luxurious' ? `<span class="rounded-full bg-gradient-to-r ${badgeClass} px-2 py-1 text-white/90 shadow-lg text-[10px]"><i class="fas fa-star"></i></span>` : ''}
            </div>
            <div class="absolute right-2 top-2">
                <div class="compare-checkbox w-6 h-6 rounded-full ${isSelected ? 'bg-rose-500' : 'bg-white/90'} backdrop-blur-sm flex items-center justify-center cursor-pointer hover:scale-110 transition shadow-lg" data-property-id="${property.id}">
                    ${isSelected ? '<svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 13l4 4L19 7"/></svg>' : '<svg class="w-4 h-4 text-slate-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>'}
                </div>
            </div>
            <div class="absolute bottom-2 left-2 right-2">
                <p class="text-xs font-semibold text-white truncate">${property.name}</p>
                <p class="text-base font-bold text-white">${formatCurrency(minConfig.price)}</p>
            </div>
        </div>
        <div class="p-3 space-y-2">
            <div class="flex items-center gap-3 text-xs text-slate-600">
                <span><i class="fas fa-bed"></i> ${minBedrooms === 0 ? 'Studio' : minBedrooms === maxBedrooms ? `${minBedrooms}` : `${minBedrooms}-${maxBedrooms}`}</span>
                <span><i class="fas fa-bath"></i> ${maxBathrooms}</span>
                <span><i class="fas fa-ruler-combined"></i> ${formatNumber(avgSqft)} sqft+</span>
            </div>
        </div>`;

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
        locationSections.innerHTML = `<div class="rounded-3xl border border-slate-200 bg-slate-50 p-10 text-center text-slate-600">
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
        header.innerHTML = `
            <div>
                <h3 class="text-base font-bold uppercase tracking-[0.1em] text-slate-700">Properties in ${location}</h3>
                <p class="text-sm text-slate-500">${locationProps.length} ${locationProps.length === 1 ? 'property' : 'properties'}</p>
            </div>
            <button class="view-all-btn text-sm font-medium text-rose-500 hover:text-rose-600 transition" data-location="${location}">
                View All -->
            </button>
        `;

        const scrollContainer = document.createElement("div");
        scrollContainer.className = "flex gap-4 overflow-x-auto pb-4 snap-x snap-mandatory scrollbar-thin scrollbar-thumb-rose-500 scrollbar-track-slate-200";
        scrollContainer.style.scrollbarWidth = "thin";

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
        `<span class="h-1.5 w-4 sm:h-2 sm:w-6 rounded-full ${index === carouselIndex ? "bg-slate-900" : "bg-slate-300"}"></span>`
    ).join("");
};

const openModal = (property) => {
    selectedProperty = property;
    carouselIndex = 0;

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
    document.getElementById("modalStatusBadge").className = `rounded-full px-3 py-1 text-xs font-semibold ${statusClass}`;
    document.getElementById("modalStatusBadge").textContent = isCompleted ? 'Completed' : 'In Progress';

    document.getElementById("modalMeta").innerHTML = `
        <span class="inline-flex items-center gap-1 sm:gap-2 text-slate-600"><span class="text-rose-400"><i class="fas fa-map-marker-alt"></i></span> <span class="text-xs sm:text-sm truncate">${property.address}</span></span>
        <span class="inline-flex items-center gap-1 sm:gap-2 text-slate-600"><span class="text-rose-400"><i class="fas fa-user"></i></span> <span class="text-xs sm:text-sm">${property.contact_name}</span></span>
        <span class="inline-flex items-center gap-1 sm:gap-2 text-slate-600"><span class="text-rose-400"><i class="fas fa-phone"></i></span> <span class="text-xs sm:text-sm">${property.contact_phone}</span></span>
    `;

    document.getElementById("modalConfigurations").innerHTML = property.configurations.map(config => `
        <div class="rounded-xl sm:rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-white p-3 sm:p-4 shadow-sm">
            <div class="flex justify-between items-start gap-2">
                <div class="flex-1 min-w-0">
                    <p class="font-semibold text-slate-900 text-sm sm:text-base truncate">${config.type}</p>
                    <p class="text-xs sm:text-sm text-slate-600 mt-1">${config.bedrooms} bed " ${config.bathrooms} bath " ${formatNumber(config.square_footage)} sqft</p>
                </div>
                <div class="text-right flex-shrink-0">
                    <p class="text-base sm:text-lg font-semibold text-rose-500">${formatCurrency(config.price)}</p>
                    <p class="text-[10px] sm:text-xs ${config.is_available ? 'text-emerald-600' : 'text-slate-400'}">${config.is_available ? ' Available' : 'Sold Out'}</p>
                </div>
            </div>
        </div>
    `).join('');

    document.getElementById("modalAmenities").innerHTML = property.amenities.map(amenity => `
        <div class="flex items-center gap-2 sm:gap-3 rounded-xl sm:rounded-2xl border border-slate-200 bg-slate-50 p-2 sm:p-3 text-xs sm:text-sm text-slate-700">
            <span class="flex h-7 w-7 sm:h-8 sm:w-8 items-center justify-center rounded-full bg-rose-100 text-rose-600 flex-shrink-0 text-sm sm:text-base">${amenity.icon}</span>
            <div class="flex-1 min-w-0">
                <p class="font-medium truncate">${amenity.name}</p>
                <p class="text-[10px] sm:text-xs text-slate-500 truncate">${amenity.description}</p>
            </div>
        </div>
    `).join('');

    // Show/hide progress section based on whether there are progress updates
    const progressSection = document.getElementById("progressSection");
    if (property.progress && property.progress.length > 0) {
        progressSection.classList.remove("hidden");
        document.getElementById("modalProgress").innerHTML = property.progress.map(progress => `
            <div class="rounded-xl sm:rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-white p-3 sm:p-4 shadow-sm space-y-3">
                <div class="flex justify-between items-start mb-2 gap-2">
                    <p class="font-semibold text-slate-900 text-sm sm:text-base">${progress.stage}</p>
                    <p class="text-rose-500 font-semibold text-sm sm:text-base flex-shrink-0">${progress.progress_percentage}%</p>
                </div>
                <div class="w-full h-1.5 sm:h-2 bg-slate-200 rounded-full overflow-hidden mb-2">
                    <div class="h-full bg-gradient-to-r from-rose-500 to-fuchsia-500" style="width: ${progress.progress_percentage}%"></div>
                </div>
                <p class="text-xs sm:text-sm text-slate-600">${progress.description}</p>
                <p class="text-[10px] sm:text-xs text-slate-400 mt-1">${new Date(progress.update_date).toLocaleDateString()}</p>
                ${progress.images && progress.images.length > 0 ? `
                    <div class="flex gap-2 overflow-x-auto pb-2 snap-x snap-mandatory scrollbar-thin scrollbar-thumb-rose-500 scrollbar-track-slate-200">
                        ${progress.images.map(img => `
                            <img src="${img.image}" alt="${img.caption || 'Progress update image'}" class="h-24 sm:h-32 w-auto rounded-lg object-cover flex-shrink-0 snap-start border border-slate-200" />
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

    // Toggle filter bar
    document.getElementById('toggleFilters').addEventListener('click', toggleFilterBar);

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
    if (selectedProperty) {
        const phoneNumber = extractPhoneNumber(selectedProperty.contact_phone);
        console.log('Extracted phone number:', phoneNumber);
        const whatsappNumber = formatWhatsAppNumber(phoneNumber);
        console.log('Formatted WhatsApp number:', whatsappNumber);
        const whatsappMessage = encodeURIComponent(`Hi! I'm interested in the property: ${selectedProperty.name} at ${selectedProperty.address}. Could you please provide more information?`);
        const whatsappLink = `https://wa.me/${whatsappNumber}?text=${whatsappMessage}`;
        console.log('WhatsApp link:', whatsappLink);
        window.open(whatsappLink, '_blank');
    }
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
    const compareButton = document.getElementById('compareButton');
    const compareCount = document.getElementById('compareCount');
    compareCount.textContent = selectedForComparison.size;

    if (selectedForComparison.size >= 2) {
        compareButton.classList.remove('hidden');
    } else {
        compareButton.classList.add('hidden');
    }
};

const showComparison = async () => {
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

try {
    initFilters();
    if (filtersVisible) {
        toggleFilterBar();
    }
    renderCards();
} catch (error) {
    console.error('Initialization error:', error);
    document.getElementById("locationSections").innerHTML = `
        <div class="rounded-3xl border border-red-200 bg-red-50 p-10 text-center text-red-600">
            <p class="font-semibold mb-2">Error loading properties</p>
            <p class="text-sm">${error.message}</p>
            <p class="text-xs mt-2">Check console for details</p>
        </div>`;
}
