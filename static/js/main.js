/**
 * Blog v2.0 — Client-Side Interactivity
 * - Dark/Light mode toggle
 * - Search modal with real-time filtering
 * - Category filter
 * - Card entrance animations (IntersectionObserver)
 * - Reading progress bar
 * - TOC toggle
 * - Share / copy link
 * - Back to top
 * - Navbar scroll effects
 * - Mobile menu
 */

(function () {
    'use strict';

    // ============================================
    // Dark Mode
    // ============================================
    const html = document.documentElement;
    const themeToggle = document.getElementById('themeToggle');
    const mobileThemeToggle = document.getElementById('mobileThemeToggle');

    function getPreferredTheme() {
        const stored = localStorage.getItem('theme');
        if (stored) return stored;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    function setTheme(theme) {
        html.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        updateThemeButtons(theme);
    }

    function updateThemeButtons(theme) {
        const icon = theme === 'dark' ? '☀️' : '🌙';
        const label = theme === 'dark' ? '浅色模式' : '深色模式';
        if (themeToggle) themeToggle.textContent = icon;
        if (mobileThemeToggle) mobileThemeToggle.textContent = `${icon} ${label}`;
    }

    function toggleTheme() {
        const current = html.getAttribute('data-theme');
        setTheme(current === 'dark' ? 'light' : 'dark');
    }

    // Initialize theme
    setTheme(getPreferredTheme());

    if (themeToggle) themeToggle.addEventListener('click', toggleTheme);
    if (mobileThemeToggle) mobileThemeToggle.addEventListener('click', toggleTheme);

    // Listen for system preference changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem('theme')) {
            setTheme(e.matches ? 'dark' : 'light');
        }
    });

    // ============================================
    // Mobile Menu
    // ============================================
    const menuToggle = document.getElementById('menuToggle');
    const mobileOverlay = document.getElementById('mobileOverlay');
    const mobileSidebar = document.getElementById('mobileSidebar');
    const mobileSidebarClose = document.getElementById('mobileSidebarClose');
    const mobileSearchBtn = document.getElementById('mobileSearchBtn');

    function openMenu() {
        document.body.classList.add('menu-open');
        mobileOverlay.classList.add('show');
        mobileSidebar.classList.add('show');
    }

    function closeMenu() {
        document.body.classList.remove('menu-open');
        mobileOverlay.classList.remove('show');
        mobileSidebar.classList.remove('show');
    }

    if (menuToggle) menuToggle.addEventListener('click', openMenu);
    if (mobileOverlay) mobileOverlay.addEventListener('click', closeMenu);
    if (mobileSidebarClose) mobileSidebarClose.addEventListener('click', closeMenu);
    if (mobileSearchBtn) {
        mobileSearchBtn.addEventListener('click', () => {
            closeMenu();
            setTimeout(openSearch, 200);
        });
    }

    // ============================================
    // Search
    // ============================================
    const searchBtn = document.getElementById('searchBtn');
    const searchModal = document.getElementById('searchModal');
    const searchInput = document.getElementById('searchInput');
    const searchClose = document.getElementById('searchClose');
    const searchResults = document.getElementById('searchResults');

    let searchTimeout = null;

    function openSearch() {
        if (!searchModal) return;
        searchModal.classList.add('show');
        document.body.style.overflow = 'hidden';
        setTimeout(() => searchInput && searchInput.focus(), 100);
    }

    function closeSearch() {
        if (!searchModal) return;
        searchModal.classList.remove('show');
        document.body.style.overflow = '';
        if (searchInput) searchInput.value = '';
        if (searchResults) searchResults.innerHTML = '<div class="search-hint">输入关键词开始搜索</div>';
    }

    function performSearch(query) {
        if (!searchResults || !window.__ARTICLES__) return;
        const q = query.trim().toLowerCase();

        if (!q) {
            searchResults.innerHTML = '<div class="search-hint">输入关键词开始搜索</div>';
            return;
        }

        const results = window.__ARTICLES__.filter(a =>
            a.title.toLowerCase().includes(q) ||
            a.quote.toLowerCase().includes(q) ||
            a.preview.toLowerCase().includes(q)
        );

        if (results.length === 0) {
            searchResults.innerHTML = '<div class="search-empty">没有找到相关文章</div>';
            return;
        }

        searchResults.innerHTML = results.map(a => `
            <a href="/post/${a.id}" target="_blank" class="search-result-item">
                <div class="search-result-title">${highlightMatch(a.title, q)}</div>
                <div class="search-result-preview">${highlightMatch(a.preview, q)}</div>
            </a>
        `).join('');
    }

    function highlightMatch(text, query) {
        if (!query) return escapeHtml(text);
        const escaped = escapeHtml(text);
        const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
        return escaped.replace(regex, '<mark style="background:rgba(230,0,18,0.15);color:var(--red);border-radius:2px;padding:0 2px;">$1</mark>');
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function escapeRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    if (searchBtn) searchBtn.addEventListener('click', openSearch);
    if (searchClose) searchClose.addEventListener('click', closeSearch);
    if (searchModal) {
        searchModal.addEventListener('click', (e) => {
            if (e.target === searchModal) closeSearch();
        });
    }
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => performSearch(searchInput.value), 300);
        });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Cmd/Ctrl + K to open search
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            openSearch();
        }
        // Escape to close
        if (e.key === 'Escape') {
            closeSearch();
            closeMenu();
        }
    });

    // ============================================
    // Category Filter
    // ============================================
    const filterTags = document.getElementById('filterTags');
    const articleList = document.getElementById('articleList');

    if (filterTags && articleList) {
        filterTags.addEventListener('click', (e) => {
            const btn = e.target.closest('.filter-tag');
            if (!btn) return;

            // Update active state
            filterTags.querySelectorAll('.filter-tag').forEach(t => t.classList.remove('active'));
            btn.classList.add('active');

            const category = btn.dataset.category;
            const cards = articleList.querySelectorAll('.article-card');

            cards.forEach(card => {
                if (category === 'all') {
                    card.style.display = '';
                } else {
                    const cats = (card.dataset.categories || '').split(',');
                    card.style.display = cats.includes(category) ? '' : 'none';
                }
            });
        });
    }

    // ============================================
    // Card Entrance Animations
    // ============================================
    function initCardAnimations() {
        const cards = document.querySelectorAll('.article-card');
        if (!cards.length) return;

        if ('IntersectionObserver' in window) {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach((entry, idx) => {
                    if (entry.isIntersecting) {
                        // Stagger: add delay based on index among currently-intersecting
                        const delay = idx * 80;
                        setTimeout(() => {
                            entry.target.classList.add('visible');
                        }, delay);
                        observer.unobserve(entry.target);
                    }
                });
            }, { threshold: 0.05, rootMargin: '0px 0px -40px 0px' });

            cards.forEach(card => observer.observe(card));
        } else {
            // Fallback: show all immediately
            cards.forEach(card => card.classList.add('visible'));
        }
    }

    initCardAnimations();

    // ============================================
    // Reading Progress Bar
    // ============================================
    const progressBar = document.getElementById('progressBar');
    const articleContent = document.getElementById('articleContent');

    function updateProgressBar() {
        if (!progressBar || !articleContent) return;
        const rect = articleContent.getBoundingClientRect();
        const windowHeight = window.innerHeight;
        const totalHeight = rect.height;
        const scrolled = -rect.top + windowHeight * 0.3;
        const progress = Math.min(100, Math.max(0, (scrolled / totalHeight) * 100));
        progressBar.style.width = progress + '%';
    }

    if (progressBar) {
        window.addEventListener('scroll', updateProgressBar, { passive: true });
        updateProgressBar();
    }

    // ============================================
    // TOC Toggle
    // ============================================
    const toc = document.getElementById('toc');
    const tocHeader = document.getElementById('tocHeader');

    if (toc && tocHeader) {
        tocHeader.addEventListener('click', () => {
            toc.classList.toggle('collapsed');
        });
    }

    // ============================================
    // Share / Copy Link
    // ============================================
    const shareBtn = document.getElementById('shareBtn');

    if (shareBtn) {
        shareBtn.addEventListener('click', () => {
            const url = window.location.href;
            if (navigator.clipboard) {
                navigator.clipboard.writeText(url).then(() => {
                    showToast('🔗 链接已复制到剪贴板');
                }).catch(() => {
                    fallbackCopy(url);
                });
            } else {
                fallbackCopy(url);
            }
        });
    }

    function fallbackCopy(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
            showToast('🔗 链接已复制到剪贴板');
        } catch {
            showToast('复制失败，请手动复制链接');
        }
        document.body.removeChild(textarea);
    }

    // ============================================
    // Toast
    // ============================================
    const toast = document.getElementById('toast');
    let toastTimer = null;

    function showToast(message, duration = 2500) {
        if (!toast) return;
        toast.textContent = message;
        toast.classList.add('show');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => {
            toast.classList.remove('show');
        }, duration);
    }

    // ============================================
    // Back to Top
    // ============================================
    const backToTop = document.getElementById('backToTop');

    if (backToTop) {
        backToTop.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    function updateBackToTop() {
        if (!backToTop) return;
        if (window.scrollY > 400) {
            backToTop.classList.add('visible');
        } else {
            backToTop.classList.remove('visible');
        }
    }

    // ============================================
    // Navbar Scroll Effect
    // ============================================
    const navbar = document.getElementById('navbar');

    function updateNavbar() {
        if (!navbar) return;
        if (window.scrollY > 10) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
    }

    // Combined scroll handler
    function onScroll() {
        updateNavbar();
        updateBackToTop();
    }

    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

})();
