const statusEl = document.getElementById("status");

function setStatus(message, kind = "") {
  statusEl.textContent = message;
  statusEl.className = `status ${kind}`.trim();
}

function formatIdr(value) {
  return new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(value);
}

async function loadConfig() {
  const token = localStorage.getItem("access_token");
  const response = await fetch("/api/v1/payments/config", {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) throw new Error("Unable to load payment configuration");
  const config = await response.json();
  document.getElementById("pro-price").textContent = formatIdr(config.pro_price_idr);
  document.getElementById("max-price").textContent = formatIdr(config.max_price_idr);
  return config;
}

async function startCheckout(plan) {
  const token = localStorage.getItem("access_token");
  if (!token) {
    setStatus("Please sign in before checkout.", "error");
    return;
  }
  setStatus("Preparing secure checkout…");
  const response = await fetch("/api/v1/payments/create", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
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
