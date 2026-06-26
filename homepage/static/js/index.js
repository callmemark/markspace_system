/**
 * =============================================
 * JAPANESE THEMED PORTFOLIO — SCRIPT.JS
 * Sakura petals • Scroll animations • Navbar effects
 * =============================================
 */

(function () {
    'use strict';

    // ─────────────────────────────────────
    // DOM READY
    // ─────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {
        initSakuraPetals();
        initScrollReveal();
        initNavbarScroll();
        initSmoothScroll();
        initActiveNavLink();
    });

    // ─────────────────────────────────────
    // 1. SAKURA PETAL ANIMATION
    // ─────────────────────────────────────
    function initSakuraPetals() {
        const petalsContainer = document.getElementById('petalsContainer');
        if (!petalsContainer) return;

        // Determine petal count based on screen width
        const screenWidth = window.innerWidth;
        let petalCount;
        if (screenWidth <= 375) {
            petalCount = 6;
        } else if (screenWidth <= 767) {
            petalCount = 10;
        } else if (screenWidth <= 991) {
            petalCount = 16;
        } else {
            petalCount = 22;
        }

        // Clear any existing petals
        petalsContainer.innerHTML = '';

        // Create petals
        for (let i = 0; i < petalCount; i++) {
            const petal = document.createElement('div');
            petal.classList.add('petal');

            // Randomize animation properties
            const duration = getRandomFloat(9, 18);
            const delay = getRandomFloat(0, 14);
            const startX = getRandomFloat(2, 94); // percentage from left
            const size = getRandomFloat(0.7, 1.3);
            const swayAmount = getRandomFloat(25, 70); // horizontal sway in px
            const rotationStart = getRandomFloat(0, 360);

            petal.style.left = startX + '%';
            petal.style.animationDuration = duration + 's';
            petal.style.animationDelay = delay + 's';
            petal.style.transform = `scale(${size}) rotate(${rotationStart}deg)`;
            petal.style.setProperty('--sway', swayAmount + 'px');

            // Add subtle variation via inline animation override
            // Each petal gets a unique animation name variation via duration/delay
            petalsContainer.appendChild(petal);
        }

        // Regenerate petals on window resize (debounced)
        let resizeTimeout;
        window.addEventListener('resize', function () {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(function () {
                initSakuraPetals();
            }, 500);
        });
    }

    // ─────────────────────────────────────
    // 2. SCROLL-BASED REVEAL ANIMATIONS
    // ─────────────────────────────────────
    function initScrollReveal() {
        const revealElements = document.querySelectorAll('.reveal-fade');

        if (!revealElements.length) return;

        // Check if Intersection Observer is supported
        if (!('IntersectionObserver' in window)) {
            // Fallback: show all elements immediately
            revealElements.forEach(function (el) {
                el.classList.add('revealed');
            });
            return;
        }

        const observerOptions = {
            root: null,
            rootMargin: '0px 0px -60px 0px', // Trigger slightly before element enters viewport
            threshold: 0.1,
        };

        const observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('revealed');
                    // Once revealed, stop observing
                    observer.unobserve(entry.target);
                }
            });
        }, observerOptions);

        revealElements.forEach(function (el) {
            observer.observe(el);
        });
    }

    // ─────────────────────────────────────
    // 3. NAVBAR SCROLL EFFECT
    // ─────────────────────────────────────
    function initNavbarScroll() {
        const navbar = document.getElementById('mainNavbar');
        if (!navbar) return;

        const scrollThreshold = 50;

        function updateNavbar() {
            const scrollY = window.scrollY || window.pageYOffset;

            if (scrollY > scrollThreshold) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        }

        // Initial check
        updateNavbar();

        // Listen for scroll
        window.addEventListener('scroll', updateNavbar, { passive: true });
    }

    // ─────────────────────────────────────
    // 4. SMOOTH SCROLL FOR ANCHOR LINKS
    // ─────────────────────────────────────
    function initSmoothScroll() {
        // Select all anchor links that point to an ID on the page
        const anchorLinks = document.querySelectorAll('a[href^="#"]');

        anchorLinks.forEach(function (link) {
            link.addEventListener('click', function (e) {
                const targetId = this.getAttribute('href');

                // Skip if it's just "#" or empty
                if (!targetId || targetId === '#') return;

                const targetElement = document.querySelector(targetId);
                if (!targetElement) return;

                e.preventDefault();

                // Close mobile navbar if open
                const navbarCollapse = document.getElementById('navbarNav');
                if (navbarCollapse && navbarCollapse.classList.contains('show')) {
                    const bsCollapse = bootstrap.Collapse.getInstance(navbarCollapse);
                    if (bsCollapse) {
                        bsCollapse.hide();
                    } else {
                        // Fallback: manually remove classes
                        navbarCollapse.classList.remove('show');
                    }
                }

                // Smooth scroll to target
                const navbarHeight = document.getElementById('mainNavbar')?.offsetHeight || 70;
                const targetPosition =
                    targetElement.getBoundingClientRect().top +
                    window.pageYOffset -
                    navbarHeight -
                    10;

                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth',
                });
            });
        });
    }

    // ─────────────────────────────────────
    // 5. ACTIVE NAV LINK ON SCROLL
    // ─────────────────────────────────────
    function initActiveNavLink() {
        const sections = document.querySelectorAll('section[id]');
        const navLinks = document.querySelectorAll('.nav-link:not(.btn-contact)');

        if (!sections.length || !navLinks.length) return;

        function updateActiveLink() {
            const scrollY = window.scrollY || window.pageYOffset;
            const navbarHeight = document.getElementById('mainNavbar')?.offsetHeight || 70;
            const offset = navbarHeight + 100;

            let currentSectionId = '';

            sections.forEach(function (section) {
                const sectionTop = section.offsetTop - offset;
                const sectionBottom = sectionTop + section.offsetHeight;

                if (scrollY >= sectionTop && scrollY < sectionBottom) {
                    currentSectionId = section.getAttribute('id');
                }
            });

            // Update active class on nav links
            navLinks.forEach(function (link) {
                link.classList.remove('active');
                const href = link.getAttribute('href');
                if (href && href.substring(1) === currentSectionId) {
                    link.classList.add('active');
                }
            });

            // If at the very top, highlight Home
            if (scrollY < 100) {
                navLinks.forEach(function (link) {
                    link.classList.remove('active');
                    const href = link.getAttribute('href');
                    if (href === '#hero') {
                        link.classList.add('active');
                    }
                });
            }
        }

        window.addEventListener('scroll', updateActiveLink, { passive: true });
        // Initial check
        updateActiveLink();
    }

    // ─────────────────────────────────────
    // UTILITY FUNCTIONS
    // ─────────────────────────────────────
    function getRandomFloat(min, max) {
        return Math.random() * (max - min) + min;
    }

    function getRandomInt(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    // ─────────────────────────────────────
    // PARALLAX-LIKE SUBTLE MOVEMENT ON MOUSE
    // (For the enso circle in hero)
    // ─────────────────────────────────────
    (function initParallaxEnso() {
        const ensoContainer = document.querySelector('.enso-container');
        const heroSection = document.querySelector('.hero-section');

        if (!ensoContainer || !heroSection) return;

        let ticking = false;

        heroSection.addEventListener('mousemove', function (e) {
            if (!ticking) {
                window.requestAnimationFrame(function () {
                    const rect = heroSection.getBoundingClientRect();
                    const centerX = rect.left + rect.width / 2;
                    const centerY = rect.top + rect.height / 2;

                    // Calculate mouse offset from center (normalized -1 to 1)
                    const offsetX = ((e.clientX - centerX) / (rect.width / 2)) * 0.5;
                    const offsetY = ((e.clientY - centerY) / (rect.height / 2)) * 0.5;

                    // Subtle movement (max ~15px)
                    const moveX = offsetX * 15;
                    const moveY = offsetY * 15;

                    ensoContainer.style.transform =
                        `translate(calc(-50% + ${moveX}px), calc(-50% + ${moveY}px))`;
                    ensoContainer.style.transition = 'transform 0.8s ease-out';

                    ticking = false;
                });
                ticking = true;
            }
        });

        // Reset position when mouse leaves
        heroSection.addEventListener('mouseleave', function () {
            ensoContainer.style.transform = 'translate(-50%, -50%)';
            ensoContainer.style.transition = 'transform 1.2s cubic-bezier(0.4, 0, 0.2, 1)';
        });
    })();

    // ─────────────────────────────────────
    // CONSOLE EASTER EGG
    // ─────────────────────────────────────
    console.log(
        '%c 禅 %c Welcome to Yuki Tanaka\'s Portfolio %c 禅 ',
        'font-size:1.2em; color:#2c3e6b;',
        'font-size:1em; color:#5a5a5a; font-family:serif;',
        'font-size:1.2em; color:#c44545;'
    );
    console.log(
        '%cCrafted with care and a touch of wabi-sabi.',
        'color:#8c8c8c; font-style:italic;'
    );

})();