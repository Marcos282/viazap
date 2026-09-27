(function () {
    'use strict';
    const script = document.currentScript;
    const measurement = script.dataset.measurement;
    const useGtm = Boolean(script.dataset.gtm);
    function read(id) {
        const node = document.getElementById(id);
        return node ? JSON.parse(node.textContent) : null;
    }
    function track(name, params) {
        if (!params || !params.tenant_id) return;
        try {
            if (measurement && typeof window.gtag === 'function') {
                window.gtag('event', name, Object.assign({}, params, {send_to: measurement}));
            } else if (useGtm) {
                window.dataLayer = window.dataLayer || [];
                window.dataLayer.push({ecommerce: null});
                window.dataLayer.push({event: name, tenant_id: params.tenant_id,
                    product_id: params.product_id, product_name: params.product_name,
                    category: params.category, share_method: params.share_method, ecommerce: params});
            }
        } catch (error) { /* Mensuração nunca interrompe compra ou compartilhamento. */ }
    }
    const product = read('productAnalyticsData');
    if (product) track('view_item', product);
    const checkout = read('checkoutAnalyticsData');
    let checkoutStarted = false;
    function beginCheckout() {
        if (!checkoutStarted && checkout && checkout.items.length) {
            track('begin_checkout', checkout);
            checkoutStarted = true;
        }
    }
    document.addEventListener('submit', function (event) {
        if (event.target.matches('[data-begin-checkout]')) beginCheckout();
    });
    document.addEventListener('click', async function (event) {
        const share = event.target.closest('[data-share-method]');
        if (share && product) {
            const method = share.dataset.shareMethod;
            const params = Object.assign({}, product, {share_method: method});
            track('share_product', params);
            if (method === 'whatsapp' || method === 'facebook') track('click_' + method, params);
            // Link HTML segue normalmente, inclusive se o Analytics não carregar.
        }
        if (event.target.closest('a[data-begin-checkout]')) beginCheckout();
        const copy = event.target.closest('[data-copy-product-link]');
        if (copy) {
            const status = document.getElementById('copyProductStatus');
            try {
                await navigator.clipboard.writeText(copy.dataset.copyProductLink);
                if (status) status.textContent = 'Link copiado!';
                track('copy_product_link', Object.assign({}, product, {share_method: 'copy'}));
            } catch (error) {
                window.prompt('Copie o link do produto:', copy.dataset.copyProductLink);
                if (status) status.textContent = 'Selecione e copie o link.';
            }
        }
    });
    if (window.jQuery) {
        window.jQuery(document).ajaxSuccess(function (_event, xhr) {
            const data = xhr.responseJSON;
            if (data && data.status === 'ok' && data.analytics) track('add_to_cart', data.analytics);
        });
    }
    const purchase = read('purchaseAnalyticsData');
    if (purchase && (measurement || useGtm)) {
        const key = 'viazap-purchase:' + purchase.transaction_id;
        let sent = false;
        try { sent = sessionStorage.getItem(key) === '1'; } catch (error) { /* storage indisponível */ }
        if (!sent) {
            track('purchase', purchase);
            try { sessionStorage.setItem(key, '1'); } catch (error) { /* GA4 usa transaction_id */ }
        }
    }
})();
