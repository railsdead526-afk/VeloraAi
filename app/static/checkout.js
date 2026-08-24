const statusEl = document.getElementById("status");

function setStatus(message, kind = "") {
  statusEl.textContent = message;
  statusEl.className = `status ${kind}`.trim();
}

function formatIdr(value) {
  return new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(value);
}

function getCookie(name) {
  const prefix = `${name}=`;
  const cookie = document.cookie.split("; ").find((item) => item.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}

function authHeaders(method = "GET") {
  const csrfToken = getCookie("velora_csrf");
  return {
    ...(method !== "GET" && csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
  };
}

async function loadConfig() {
  const response = await fetch("/api/v1/payments/config", {
    credentials: "include",
    headers: authHeaders(),
  });
  if (!response.ok) throw new Error("Unable to load payment configuration");
  const config = await response.json();
  document.getElementById("pro-price").textContent = formatIdr(config.pro_price_idr);
  document.getElementById("max-price").textContent = formatIdr(config.max_price_idr);
  return config;
}

async function startCheckout(plan) {
  setStatus("Preparing secure checkout…");
  const response = await fetch("/api/v1/payments/create", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders("POST"),
    },
    body: JSON.stringify({ plan }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Unable to start checkout");
  }
  const payment = await response.json();
  if (!window.snap) throw new Error("Payment checkout is unavailable");

  setStatus("Opening secure Midtrans checkout…");
  window.snap.pay(payment.snap_token, {
    onSuccess: () => setStatus("Payment received. Your plan will activate after verification.", "success"),
    onPending: () => setStatus("Payment is pending. Complete the payment to activate your plan."),
    onError: () => setStatus("Payment failed. Please try again.", "error"),
    onClose: () => setStatus("Checkout closed."),
  });
}

document.querySelectorAll(".checkout-button").forEach((button) => {
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await startCheckout(button.dataset.plan);
    } catch (error) {
      setStatus(error.message || "Unable to start checkout", "error");
    } finally {
      button.disabled = false;
    }
  });
});

loadConfig().catch((error) => setStatus(error.message, "error"));
