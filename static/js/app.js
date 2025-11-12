// === SwiftServe Add to Cart ===
function addToCart(e, form) {
  e.preventDefault();
  const fd = new FormData(form);
  fetch(form.action, { method: 'POST', body: fd })
    .then(r => r.json())
    .then(d => {
      if (d.ok) alert('Added to cart! Items: ' + d.count);
      else alert('Could not add');
    })
    .catch(() => alert('Network error'));
  return false;
}

// === SwiftServe Hover Video Logic ===
document.addEventListener("DOMContentLoaded", () => {
  const itemCards = document.querySelectorAll(".item-card");

  itemCards.forEach(card => {
    const video = card.querySelector(".item-video");
    if (!video) return;

    // Mouse hover start
    card.addEventListener("mouseenter", () => {
      video.currentTime = 0; // start from beginning
      video.play().catch(() => { }); // ignore autoplay errors
      card.classList.add("playing");
    });

    // Mouse hover end
    card.addEventListener("mouseleave", () => {
      video.pause();
      card.classList.remove("playing");
    });
  });
});

// === Single SocketIO Instance ===
const socket = io();

// --- Real-time Flash Notifications (Top Right) ---
socket.on('order_update', data => {
  console.log('Order update received:', data);
  const flash = document.createElement('div');
  flash.className = 'flash-live';
  flash.innerHTML = `Order #${data.order_id} → <b>${data.status}</b>`;
  document.body.appendChild(flash);
  setTimeout(() => flash.remove(), 4000);

  // --- If this page has an order details section ---
  const orderDiv = document.querySelector('[data-order-id]');
  if (orderDiv && parseInt(orderDiv.dataset.orderId) === data.order_id) {
    const statusEl = document.getElementById('order-status');
    if (statusEl) statusEl.textContent = data.status;
  }
});

socket.on('connect', () => console.log('Socket connected ✅'));
