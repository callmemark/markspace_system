(function() {
    /* ── STAR FIELD ── */
    const canvas = document.getElementById('star-canvas');
    const ctx = canvas.getContext('2d');

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', () => { resize(); buildStars(); });

    let stars = [];
    function buildStars() {
        const n = Math.floor((canvas.width * canvas.height) / 3500);
        stars = Array.from({ length: n }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        r: Math.random() * 1.2,
        alpha: Math.random() * 0.8 + 0.1,
        speed: Math.random() * 0.3 + 0.05,
        twinkleSpeed: Math.random() * 0.015 + 0.005,
        twinklePhase: Math.random() * Math.PI * 2
        }));
    }
    buildStars();

    // A few large "bright" stars
    const brightStars = Array.from({ length: 6 }, () => ({
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        r: Math.random() * 1.5 + 1.2,
        alpha: 0.9,
        twinklePhase: Math.random() * Math.PI * 2
    }));

    let t = 0;
    function drawStars() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        t += 0.016;

        // Dim stars
        stars.forEach(s => {
        const tw = Math.sin(t * s.twinkleSpeed * 60 + s.twinklePhase) * 0.3;
        ctx.beginPath();
        ctx.arc(s.x, s.y + t * s.speed % canvas.height, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(220, 232, 255, ${Math.max(0.05, s.alpha + tw)})`;
        ctx.fill();
        });

        // Bright stars with cross-hatch diffraction spike
        brightStars.forEach(s => {
        const tw = Math.sin(t * 0.4 + s.twinklePhase) * 0.2;
        const a = s.alpha + tw;
        // Core
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(220, 232, 255, ${a})`;
        ctx.fill();
        // Spikes
        ctx.strokeStyle = `rgba(220, 232, 255, ${a * 0.35})`;
        ctx.lineWidth = 0.5;
        ctx.beginPath(); ctx.moveTo(s.x - s.r * 5, s.y); ctx.lineTo(s.x + s.r * 5, s.y); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(s.x, s.y - s.r * 5); ctx.lineTo(s.x, s.y + s.r * 5); ctx.stroke();
        });

        requestAnimationFrame(drawStars);
    }
    drawStars();


    /* ── CUSTOM CURSOR ── */
    const cursor = document.getElementById('cursor');
    const ring = document.getElementById('cursor-ring');
    let mx = -100, my = -100, rx = -100, ry = -100;

    document.addEventListener('mousemove', e => {
        mx = e.clientX;
        my = e.clientY;
        cursor.style.left = (mx - 4) + 'px';
        cursor.style.top  = (my - 4) + 'px';
    });

    function animRing() {
        rx += (mx - rx - 16) * 0.12;
        ry += (my - ry - 16) * 0.12;
        ring.style.left = rx + 'px';
        ring.style.top  = ry + 'px';
        requestAnimationFrame(animRing);
    }
    animRing();

    // Expand on hoverable elements
    document.querySelectorAll('a, button, .skill-card, .approach-item, .project-card, .portfolio-img-preview').forEach(el => {
        el.addEventListener('mouseenter', () => {
            ring.style.width = '56px';
            ring.style.height = '56px';
        });
        el.addEventListener('mouseleave', () => {
            ring.style.width = '32px';
            ring.style.height = '32px';
        });
    });


    /* ── NAV SCROLL EFFECT ── */
    const nav = document.getElementById('main-nav');
    window.addEventListener('scroll', () => {
        nav.classList.toggle('scrolled', window.scrollY > 60);
    });


    /* ── GSAP SCROLL ANIMATIONS ── */
    gsap.registerPlugin(ScrollTrigger);

    // Skills grid stagger
    gsap.from('.skill-card', {
        scrollTrigger: { trigger: '.skills-grid', start: 'top 80%' },
        opacity: 0,
        y: 24,
        stagger: 0.1,
        duration: 0.6,
        ease: 'power2.out'
    });

    // Approach grid stagger
    gsap.from('.approach-item', {
        scrollTrigger: { trigger: '.approach-grid', start: 'top 80%' },
        opacity: 0,
        y: 24,
        stagger: 0.1,
        duration: 0.6,
        ease: 'power2.out'
    });

    // Astronomy banner
    gsap.from('.astro-stat', {
        scrollTrigger: { trigger: '.astronomy-banner', start: 'top 80%' },
        opacity: 0,
        y: 16,
        stagger: 0.15,
        duration: 0.6,
        ease: 'power2.out'
    });

    // Section headers
    gsap.utils.toArray('.section-header').forEach(el => {
        gsap.from(el, {
        scrollTrigger: { trigger: el, start: 'top 85%' },
        opacity: 0,
        x: -20,
        duration: 0.7,
        ease: 'power2.out'
        });
    });

    gsap.from('#portfolio', {
        scrollTrigger: { trigger: '#portfolio', start: 'top 80%' },
        opacity: 0,
        y: 24,
        stagger: 0.1,
        duration: 0.6,
        ease: 'power2.out'
    });

    // Timeline in-view class
    const timelineItems = document.querySelectorAll('.timeline-item');
    const tObserver = new IntersectionObserver(entries => {
        entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('in-view'); });
    }, { threshold: 0.2 });
    timelineItems.forEach(el => tObserver.observe(el));


    /* ── SECTION HEADER LINE ANIMATION ── */
    gsap.utils.toArray('.section-line').forEach(el => {
        gsap.from(el, {
        scrollTrigger: { trigger: el, start: 'top 85%' },
        scaleX: 0,
        transformOrigin: 'left',
        duration: 1.2,
        ease: 'power3.out'
        });
    });
})();