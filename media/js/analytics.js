/*
 * Initialize Google Analytics 4 while respecting Do Not Track.
 * This stays in a self-hosted file so CSP does not need unsafe-inline.
 */
var DNT = navigator.doNotTrack || window.doNotTrack || navigator.msDoNotTrack || window.msDoNotTrack;
var GA_MEASUREMENT_ID = 'G-E0B6CTN92P';

if ((DNT != '1') && (DNT != 'yes')) {
    window.dataLayer = window.dataLayer || [];
    window.gtag = function() {
        window.dataLayer.push(arguments);
    };

    window.gtag('js', new Date());
    window.gtag('config', GA_MEASUREMENT_ID);

    var gaScript = document.createElement('script');
    gaScript.async = true;
    gaScript.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_MEASUREMENT_ID;
    document.head.appendChild(gaScript);
}
