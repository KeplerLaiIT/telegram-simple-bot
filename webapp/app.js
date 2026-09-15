const telegram = window.Telegram?.WebApp;
const cityStorageKey = "telegram-bot-city";
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Moscow";

if (telegram) {
  telegram.ready();
  telegram.expand();
}

const user = telegram?.initDataUnsafe?.user || {};
const state = { city: localStorage.getItem(cityStorageKey) || "" };
const weatherCodes = {
  0: "Ясно", 1: "Преимущественно ясно", 2: "Переменная облачность", 3: "Пасмурно",
  45: "Туман", 48: "Изморозь", 51: "Лёгкая морось", 61: "Небольшой дождь",
  63: "Дождь", 65: "Сильный дождь", 71: "Небольшой снег", 73: "Снег",
  75: "Сильный снег", 80: "Ливень", 81: "Сильный ливень", 82: "Очень сильный ливень",
  95: "Гроза", 96: "Гроза с градом", 99: "Сильная гроза с градом",
};

const $ = (selector) => document.querySelector(selector);

function showToast(message) {
  $("#toast").textContent = message;
  window.setTimeout(() => { $("#toast").textContent = ""; }, 3500);
}

function showView(viewName) {
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active-view"));
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.view === viewName));
  $(`#${viewName}-view`).classList.add("active-view");
  if (viewName === "rates") loadRates();
  if (viewName === "profile") renderProfile();
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error("network");
  return response.json();
}

async function loadWeather(city) {
  const result = $("#weather-result");
  result.className = "result-panel";
  result.textContent = "Загружаю погоду...";
  try {
    const location = await getJson(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(city)}&count=1&language=ru&format=json`);
    if (!location.results?.length) throw new Error("city");
    const place = location.results[0];
    const forecast = await getJson(`https://api.open-meteo.com/v1/forecast?latitude=${place.latitude}&longitude=${place.longitude}&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code&timezone=auto`);
    const current = forecast.current;
    state.city = place.name;
    localStorage.setItem(cityStorageKey, state.city);
    result.innerHTML = `<strong>${place.name}, ${place.country || "Россия"}</strong><br>${weatherCodes[current.weather_code] || "Неизвестные условия"}<br>Температура: ${current.temperature_2m} °C<br>Ощущается как: ${current.apparent_temperature} °C<br>Влажность: ${current.relative_humidity_2m}%`;
    $("#home-city").textContent = state.city;
    renderProfile();
  } catch (error) {
    result.textContent = error.message === "city" ? "Город не найден. Проверь написание." : "Не удалось загрузить погоду. Проверь интернет-соединение.";
  }
}

async function loadRates() {
  const cards = document.querySelectorAll(".rate-card strong");
  cards.forEach((card) => { card.textContent = "..."; });
  try {
    const data = await getJson("https://open.er-api.com/v6/latest/USD");
    cards[0].textContent = `${data.rates.RUB.toFixed(2)} RUB`;
    cards[1].textContent = `${(data.rates.RUB / data.rates.EUR).toFixed(2)} RUB`;
  } catch {
    cards.forEach((card) => { card.textContent = "Ошибка"; });
    showToast("Не удалось обновить курсы валют.");
  }
}

function renderProfile() {
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ") || "Гость";
  $("#profile-name").textContent = name;
  $("#profile-username").textContent = user.username ? `@${user.username}` : "не указан";
  $("#profile-city").textContent = state.city || "не указан";
  $("#profile-timezone").textContent = timezone;
  $("#profile-local-time").textContent = new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short", timeStyle: "short", timeZone: timezone,
  }).format(new Date());
  $("#welcome-title").textContent = `Привет, ${user.first_name || "друг"}`;
  $("#home-city").textContent = state.city || "Выбрать город";
}

$("#sync-timezone").addEventListener("click", () => {
  if (!telegram) {
    showToast(`Часовой пояс определён: ${timezone}`);
    return;
  }
  telegram.sendData(JSON.stringify({ timezone }));
});

document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
document.querySelectorAll("[data-view-target]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.viewTarget)));
$("#weather-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const city = $("#city-input").value.trim();
  if (!city) { showToast("Введи название города."); return; }
  loadWeather(city);
});
$("#rates-button").addEventListener("click", loadRates);
$("#today").textContent = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" }).format(new Date());
renderProfile();
if (state.city) loadWeather(state.city);