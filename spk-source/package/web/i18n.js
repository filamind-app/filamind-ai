// Tiny i18n loader. Reads ?lang=, localStorage, or navigator.language.
(function () {
    const LS_LANG = "filamindai_lang";
    const LS_THEME = "filamindai_theme";

    function detectLang() {
        const qs = new URLSearchParams(location.search);
        if (qs.get("lang")) return qs.get("lang");
        const saved = localStorage.getItem(LS_LANG);
        if (saved) return saved;
        const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
        return ["en", "ar"].includes(nav) ? nav : "en";
    }

    function applyTheme() {
        const t = localStorage.getItem(LS_THEME) || "light";
        document.documentElement.setAttribute("data-theme", t);
    }

    function setDir(lang) {
        document.documentElement.lang = lang;
        document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    }

    async function loadI18n() {
        applyTheme();
        const lang = detectLang();
        setDir(lang);
        try {
            const r = await fetch("/api/i18n?lang=" + encodeURIComponent(lang));
            window.I18N = r.ok ? await r.json() : {};
        } catch (e) {
            window.I18N = {};
        }
        applyTranslations();
        wireLangButton(lang);
    }

    function t(key) {
        const parts = key.split(".");
        let cur = window.I18N || {};
        for (const p of parts) {
            if (cur && typeof cur === "object" && p in cur) cur = cur[p];
            else return null;
        }
        return typeof cur === "string" ? cur : null;
    }

    function applyTranslations() {
        document.querySelectorAll("[data-i18n]").forEach(el => {
            const val = t(el.dataset.i18n);
            if (val) {
                if (el.tagName === "INPUT" && (el.type === "text" || el.type === "password")) {
                    el.placeholder = val;
                } else {
                    el.textContent = val;
                }
            }
        });
        document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
            const val = t(el.dataset.i18nPlaceholder);
            if (val) el.placeholder = val;
        });
        document.querySelectorAll("[data-i18n-title]").forEach(el => {
            const val = t(el.dataset.i18nTitle);
            if (val) el.title = val;
        });
    }

    function wireLangButton(currentLang) {
        const btn = document.getElementById("langBtn");
        if (!btn) return;
        btn.textContent = currentLang === "ar" ? "عربي" : "EN";
        btn.addEventListener("click", () => {
            const next = currentLang === "ar" ? "en" : "ar";
            localStorage.setItem(LS_LANG, next);
            location.reload();
        });
    }

    window.t = t;
    window.applyI18n = applyTranslations;
    window.FilamindI18n = { detectLang, loadI18n };

    document.addEventListener("DOMContentLoaded", loadI18n);
})();
