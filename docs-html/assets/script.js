// Ticketing Infrastructure Security Simulator Docs Script
document.addEventListener('DOMContentLoaded', () => {
  // 1. Highlight Active Nav Item
  const currentPath = window.location.pathname.split('/').pop() || 'index.html';
  const navLinks = document.querySelectorAll('.nav-item a');
  
  navLinks.forEach(link => {
    const href = link.getAttribute('href');
    if (href === currentPath || (currentPath === '' && href === 'index.html')) {
      link.parentElement.classList.add('active');
    } else {
      link.parentElement.classList.remove('active');
    }
  });

  // 2. Mobile Menu Toggle
  const menuToggle = document.getElementById('menuToggle');
  const sidebar = document.getElementById('sidebar');

  if (menuToggle && sidebar) {
    menuToggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
    });

    document.addEventListener('click', (e) => {
      if (window.innerWidth <= 900 && !sidebar.contains(e.target) && !menuToggle.contains(e.target)) {
        sidebar.classList.remove('open');
      }
    });
  }

  // 3. Search Filter
  const searchInput = document.getElementById('searchInput');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const term = e.target.value.toLowerCase().trim();
      const cards = document.querySelectorAll('.card, .table-responsive, pre');
      
      cards.forEach(card => {
        const text = card.textContent.toLowerCase();
        if (term === '' || text.includes(term)) {
          card.style.display = '';
        } else {
          card.style.display = 'none';
        }
      });
    });
  }

  // 4. Image Lightbox Modal
  const modalHTML = `
    <div id="imgModal" class="img-modal">
      <div class="img-modal-overlay"></div>
      <div class="img-modal-content">
        <button class="img-modal-close" aria-label="Close">&times;</button>
        <img id="imgModalSrc" src="" alt="Full view">
        <div id="imgModalCaption" class="img-modal-caption"></div>
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', modalHTML);

  const modal = document.getElementById('imgModal');
  const modalImg = document.getElementById('imgModalSrc');
  const modalCaption = document.getElementById('imgModalCaption');
  const modalClose = document.querySelector('.img-modal-close');
  const modalOverlay = document.querySelector('.img-modal-overlay');

  document.querySelectorAll('.gallery-card img').forEach(img => {
    img.addEventListener('click', (e) => {
      e.preventDefault();
      modalImg.src = img.src;
      const captionText = img.closest('.gallery-card').querySelector('h4')?.innerText || img.alt;
      modalCaption.innerText = captionText;
      modal.classList.add('active');
      document.body.style.overflow = 'hidden';
    });
  });

  const closeModal = () => {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  };

  if (modalClose) modalClose.addEventListener('click', closeModal);
  if (modalOverlay) modalOverlay.addEventListener('click', closeModal);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.classList.contains('active')) {
      closeModal();
    }
  });

  // 5. Code Block Copy Button
  document.querySelectorAll('pre').forEach(pre => {
    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-code-btn';
    copyBtn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      <span>คัดลอก</span>
    `;
    pre.style.position = 'relative';
    pre.appendChild(copyBtn);

    copyBtn.addEventListener('click', () => {
      const code = pre.querySelector('code')?.innerText || pre.innerText;
      navigator.clipboard.writeText(code).then(() => {
        copyBtn.classList.add('copied');
        copyBtn.querySelector('span').innerText = 'สำเร็จ!';
        setTimeout(() => {
          copyBtn.classList.remove('copied');
          copyBtn.querySelector('span').innerText = 'คัดลอก';
        }, 2000);
      });
    });
  });
});
