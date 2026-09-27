(function () {
    'use strict';
    function track(name) {
        if (typeof window.gtag === 'function') {
            window.gtag('event', name, {send_to: 'G-C4BWMDXFPQ'});
        }
    }
    document.addEventListener('click', function (event) {
        const link = event.target.closest('a[href]');
        if (!link) return;
        const url = new URL(link.href, window.location.href);
        if (url.origin === window.location.origin && url.pathname === '/register/') {
            track('sign_up_click');
            track('tenant_signup_start');
        } else if (url.origin === window.location.origin && url.pathname === '/login/') {
            track('login_click');
        } else if (url.hostname === 'wa.me' || url.hostname === 'api.whatsapp.com') {
            track('whatsapp_contact_click');
        }
    });
    const pricing = document.getElementById('planos');
    if (pricing && 'IntersectionObserver' in window) {
        const observer = new IntersectionObserver(function (entries) {
            if (entries.some(entry => entry.isIntersecting)) {
                track('pricing_view');
                observer.disconnect();
            }
        }, {threshold: 0.25});
        observer.observe(pricing);
    }
})();
