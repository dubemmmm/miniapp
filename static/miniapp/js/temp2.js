// Progressive enhancements for the temp2 landing-page preview.
(function () {
    const propertyById = new Map(properties.map(property => [String(property.id), property]));

    const compactRange = (values, unit, singular) => {
        const valid = values.filter(value => Number.isFinite(value));
        if (!valid.length) return '';
        const min = Math.min(...valid);
        const max = Math.max(...valid);
        const value = min === max ? `${min}` : `${min}-${max}`;
        const label = min === max && min === 1 ? singular : unit;
        return `${value} ${label}`;
    };

    const formatSqft = configurations => {
        const values = configurations
            .map(config => Number(config.square_footage))
            .filter(value => Number.isFinite(value) && value > 0);
        if (!values.length) return '';
        const min = Math.min(...values);
        const max = Math.max(...values);
        const formatted = min === max
            ? min.toLocaleString('en-US')
            : `${min.toLocaleString('en-US')}-${max.toLocaleString('en-US')}`;
        return `${formatted} sqm`;
    };

    const markMissingImage = image => {
        const wrap = image.closest('.card-img-wrap');
        if (wrap) wrap.classList.add('is-missing-image');
    };

    const enhanceCard = card => {
        if (card.dataset.temp2Enhanced === 'true') return;

        const compareControl = card.querySelector('.compare-checkbox');
        const property = compareControl
            ? propertyById.get(String(compareControl.dataset.propertyId))
            : null;
        if (!property) return;

        card.dataset.temp2Enhanced = 'true';
        card.tabIndex = 0;
        card.setAttribute('aria-label', `View ${property.name}`);

        const title = card.querySelector('.card-title');
        const subtitle = card.querySelector('.card-subtitle');
        const price = card.querySelector('.card-price');
        const info = card.querySelector('.card-info');
        const neighborhood = (property.address || property.location || '').split(',')[0].trim();

        if (title) title.textContent = property.name;
        if (subtitle) subtitle.textContent = neighborhood || property.location || 'Lagos';
        if (info && subtitle && price) info.insertBefore(subtitle, price);

        const configurations = property.configurations || [];
        const specs = [
            compactRange(configurations.map(config => Number(config.bedrooms)), 'beds', 'bed'),
            compactRange(configurations.map(config => Number(config.bathrooms)), 'baths', 'bath'),
            formatSqft(configurations),
        ].filter(Boolean);

        if (info && price && specs.length) {
            const specsRow = document.createElement('div');
            specsRow.className = 'temp2-specs';
            specs.forEach(spec => {
                const item = document.createElement('span');
                item.textContent = spec;
                specsRow.appendChild(item);
            });
            price.insertAdjacentElement('afterend', specsRow);
        }

        const image = card.querySelector('.card-img');
        if (image) {
            image.addEventListener('error', () => markMissingImage(image), { once: true });
            if (!image.getAttribute('src') || (image.complete && image.naturalWidth === 0)) {
                markMissingImage(image);
            }
        }

        card.addEventListener('keydown', event => {
            if ((event.key === 'Enter' || event.key === ' ') && event.target === card) {
                event.preventDefault();
                card.click();
            }
        });
    };

    const enhanceCards = root => {
        root.querySelectorAll('.card-split').forEach(enhanceCard);
    };

    const watchCards = container => {
        if (!container) return;
        enhanceCards(container);
        new MutationObserver(() => enhanceCards(container)).observe(container, {
            childList: true,
            subtree: true,
        });
    };

    const currencyLabel = document.getElementById('currencyLabel');
    const normalizeCurrencyLabel = () => {
        if (!currencyLabel) return;
        const target = currencyLabel.textContent.includes('NGN') ? 'NGN' : 'USD';
        if (currencyLabel.textContent !== target) currencyLabel.textContent = target;
        currencyLabel.closest('button')?.setAttribute('title', `Display prices in ${target}`);
    };

    if (currencyLabel) {
        normalizeCurrencyLabel();
        new MutationObserver(normalizeCurrencyLabel).observe(currencyLabel, {
            childList: true,
            characterData: true,
            subtree: true,
        });
    }

    const priceRangeLabel = document.getElementById('priceRangeLabel');
    const quickPriceLabel = document.getElementById('temp2PriceLabel');
    const syncQuickPrice = () => {
        if (!priceRangeLabel || !quickPriceLabel) return;
        const isDefaultRange = filters.priceRange[0] === filterRanges.min_price
            && filters.priceRange[1] === filterRanges.max_price;
        quickPriceLabel.textContent = isDefaultRange ? 'Any price' : priceRangeLabel.textContent;
    };

    if (priceRangeLabel && quickPriceLabel) {
        syncQuickPrice();
        new MutationObserver(syncQuickPrice).observe(priceRangeLabel, {
            childList: true,
            characterData: true,
            subtree: true,
        });
    }

    document.getElementById('temp2PriceButton')?.addEventListener('click', () => {
        const panel = document.getElementById('filterContent');
        if (panel && (panel.style.maxHeight === '0px' || panel.style.maxHeight === '0')) {
            document.getElementById('toggleFilters')?.click();
        }
        document.getElementById('minPriceRange')?.focus();
    });

    const actionRow = document.getElementById('contactBtn')?.parentElement;
    const fullPropertyLink = document.createElement('a');
    fullPropertyLink.id = 'temp2FullPropertyBtn';
    fullPropertyLink.className = 'temp2-full-property';
    fullPropertyLink.textContent = 'Full details';
    fullPropertyLink.href = '#';
    if (actionRow) actionRow.appendChild(fullPropertyLink);

    const setFullPropertyLink = propertyId => {
        if (!propertyId || !propertyById.has(String(propertyId))) return;
        fullPropertyLink.href = `/property/${propertyId}/`;
    };

    document.addEventListener('click', event => {
        const card = event.target.closest('.card-split');
        const cardPropertyId = card?.querySelector('.compare-checkbox')?.dataset.propertyId;
        if (cardPropertyId) setFullPropertyLink(cardPropertyId);

        if (event.target.closest('#heroFeaturedCard')) {
            const featured = properties.find(property => property.luxury_status === 'luxurious') || properties[0];
            if (featured) setFullPropertyLink(featured.id);
        }
    }, true);

    const modal = document.getElementById('propertyModal');
    if (modal) {
        new MutationObserver(() => {
            if (!modal.classList.contains('hidden') && typeof selectedProperty !== 'undefined' && selectedProperty) {
                setFullPropertyLink(selectedProperty.id);
            }
        }).observe(modal, { attributes: true, attributeFilter: ['class'] });
    }

    watchCards(document.getElementById('locationSections'));
    watchCards(document.getElementById('locationViewAllGrid'));
})();
