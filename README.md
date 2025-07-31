# 🎮 HTML5 Game Scraper

A Python-based web scraper that extracts game details (name, description, image, and playable game URL) from three major platforms:

- [Poki](https://poki.com)
- [GameDistribution](https://gamedistribution.com)
- [GamePix](https://www.gamepix.com)

It uses `Selenium`, `aiohttp`, `asyncio`, and `BeautifulSoup` to handle both static and dynamically-rendered content, then saves the data to a CSV file.

---

## 🚀 Features

- ✅ Scrapes game **name**, **description**, **image**, **game URL**, and **game API URL**
- ✅ Supports 3 major HTML5 game websites
- ✅ Uses **undetected_chromedriver** for dynamic content
- ✅ Performs concurrent HTTP requests using **aiohttp** and **asyncio**
- ✅ Saves extracted data into a well-structured CSV file

---

## 📦 Output

The script creates a CSV file named `games_data.csv` with the following fields:

- Name
- URL
- Description
- Image URL
- Game API URL
- Website
- Timestamp

---

## 🧰 Requirements

Install dependencies using pip:

```bash
pip install undetected-chromedriver selenium beautifulsoup4 aiohttp
