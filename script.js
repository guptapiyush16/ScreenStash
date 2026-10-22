/**
 * ScreenStash Landing Page Interactive Script
 * Handles command copying, interactive filter tabs, and download triggers.
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. Copy command to clipboard with visual feedback
  const copyButtons = document.querySelectorAll('.copy-btn-trigger');

  copyButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-target');
      const textToCopy = document.getElementById(targetId)?.innerText.trim();

      if (textToCopy) {
        navigator.clipboard.writeText(textToCopy).then(() => {
          const originalText = btn.innerText;
          btn.innerText = 'Copied! ✓';
          btn.style.background = '#cbfb4d';
          btn.style.color = '#141413';
          btn.style.borderColor = '#98cc12';

          setTimeout(() => {
            btn.innerText = originalText;
            btn.style.background = '';
            btn.style.color = '';
            btn.style.borderColor = '';
          }, 2200);
        });
      }
    });
  });

  // 2. Interactive Peek Inside Category Tabs
  const filterPills = document.querySelectorAll('.filter-pill');
  const stashCards = document.querySelectorAll('.stash-card-preview');

  filterPills.forEach((pill) => {
    pill.addEventListener('click', () => {
      // Set active pill
      filterPills.forEach((p) => p.classList.remove('active'));
      pill.classList.add('active');

      const selectedCategory = pill.getAttribute('data-category');

      // Filter preview cards
      stashCards.forEach((card) => {
        const cardCat = card.getAttribute('data-category');
        if (selectedCategory === 'all' || cardCat === selectedCategory) {
          card.style.display = 'block';
          card.style.animation = 'fadeIn 0.3s ease forwards';
        } else {
          card.style.display = 'none';
        }
      });
    });
  });

  // 3. Smooth scrolling for anchor links
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener('click', function (e) {
      const target = document.querySelector(this.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });
});
