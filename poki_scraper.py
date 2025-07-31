import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import csv
import time
import sys
import concurrent.futures
import asyncio
import aiohttp
import json
from urllib.parse import urljoin
import re
import os

def setup_driver():
    """Set up and return an undetected Chrome WebDriver instance"""
    options = uc.ChromeOptions()
    options.headless = True
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-images')  # Disable image loading for faster scraping
    options.add_argument('--disable-javascript')  # Disable JavaScript where possible
    
    try:
        driver = uc.Chrome(options=options)
        return driver
    except Exception as e:
        print(f"Error setting up Chrome driver: {e}")
        sys.exit(1)

async def fetch_page(session, url):
    """Fetch a page using aiohttp"""
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.text()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None

async def process_game_batch(session, games, base_url):
    """Process a batch of games concurrently"""
    tasks = []
    for game in games:
        game_url = game.get('href', '')
        if not game_url:
            continue
        if not game_url.startswith('http'):
            game_url = urljoin(base_url, game_url)
        tasks.append(fetch_page(session, game_url))
    
    return await asyncio.gather(*tasks)

async def scrape_website(url):
    """Scrape games from a website"""
    print(f"\nStarting to scrape {url}...")
    
    async with aiohttp.ClientSession() as session:
        # Get the initial page HTML
        html = await fetch_page(session, url)
        if not html:
            print(f"Failed to get HTML from {url}")
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        games = []
        
        if 'poki.com' in url:
            # For Poki, get game links from the homepage
            game_links = []
            for a in soup.select('a[href*="/g/"]'):
                href = a.get('href', '')
                if href and '/g/' in href:
                    if not href.startswith('http'):
                        href = urljoin('https://poki.com', href)
                    game_links.append(href)
            
            print(f"Found {len(game_links)} games")
            
            # Process games in chunks
            chunk_size = 10
            for i in range(0, len(game_links), chunk_size):
                chunk = game_links[i:i + chunk_size]
                tasks = []
                for link in chunk:
                    tasks.append(fetch_page(session, link))
                chunk_results = await asyncio.gather(*tasks)
                
                for html, link in zip(chunk_results, chunk):
                    if html:
                        game_info = extract_game_info(html, link)
                        if game_info:
                            games.append(game_info)
                print(f"Processed {min(i + chunk_size, len(game_links))} games so far...")
        else:
            # Setup Chrome driver for initial page load
            driver = setup_driver()
            try:
                driver.get(url)
                time.sleep(3)  # Wait a bit longer for initial load
                
                # Scroll quickly to load more content
                last_height = driver.execute_script("return document.body.scrollHeight")
                scroll_attempts = 0
                max_scroll_attempts = 5  # Increase scroll attempts to get more games
                
                while scroll_attempts < max_scroll_attempts:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        break
                    last_height = new_height
                    scroll_attempts += 1
                
                # Get all game links based on the website
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                
                # Different selectors for different websites
                games = []
                if 'poki.com' in url:
                    # Poki-specific selectors
                    games = (
                        soup.select('a[href*="/g/"]') or  # Main game links
                        soup.select('.game-tile a') or    # Game tiles
                        soup.select('.game-card a') or    # Game cards
                        soup.select('article.game-item a') or  # Game items
                        soup.select('[class*="GameTile"] a') or  # React components
                        soup.select('[class*="game-wrapper"] a')  # General game wrappers
                    )
                elif 'gamepix.com' in url:
                    # GamePix-specific selectors
                    games = (
                        soup.select('a[href*="/play/"]') or  # Main game links
                        soup.select('.game-card a') or    # Game cards
                        soup.select('[class*="game"] a')  # General game elements
                    )
                else:
                    # Game Distribution selectors
                    games = (
                        soup.select('a[href*="/games/"]') or 
                        soup.select('.game-card a') or 
                        soup.select('[class*="game"] a')
                    )
                
                print(f"Found {len(games)} games")
                
                # Process games in batches using aiohttp
                for i in range(0, len(games), 10):
                    batch = games[i:i + 10]
                    responses = await process_game_batch(session, batch, url)
                    
                    # Process responses in parallel using ThreadPoolExecutor
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        futures = []
                        for html, game in zip(responses, batch):
                            if html:  # Only process if we got a response
                                game_url = game.get('href', '')
                                if not game_url:
                                    continue
                                    
                                # Handle relative URLs
                                if not game_url.startswith('http'):
                                    if 'poki.com' in url:
                                        game_url = urljoin('https://poki.com', game_url)
                                    elif 'gamepix.com' in url:
                                        game_url = urljoin('https://www.gamepix.com', game_url)
                                    else:
                                        game_url = urljoin('https://gamedistribution.com', game_url)
                                
                                futures.append(
                                    executor.submit(extract_game_info, html, game_url)
                                )
                        
                        for future in concurrent.futures.as_completed(futures):
                            result = future.result()
                            if result:
                                games.append(result)
                    
                    print(f"Processed {len(games)} games so far...")
        
            except Exception as e:
                print(f"Error scraping {url}: {e}")
            finally:
                driver.quit()
    
    return games

def extract_game_info(html, url):
    """Extract game information from HTML"""
    if not html:
        return None
    
    soup = BeautifulSoup(html, 'html.parser')
    is_poki = 'poki.com' in url
    is_gamepix = 'gamepix.com' in url
    
    # For Poki, extract iframe src as game API URL
    if is_poki:
        try:
            # Find the game iframe
            iframe = soup.find('iframe', id='game-element')
            if iframe and iframe.get('src'):
                game_api_url = iframe.get('src')
                if not game_api_url.startswith('http'):
                    game_api_url = urljoin('https://poki.com', game_api_url)
                
                # Get other game information
                name = None
                for selector in ['h1', 'meta[property="og:title"]', 'title']:
                    elem = soup.select_one(selector)
                    if elem:
                        name = elem.get('content', '') or elem.text.strip()
                        if name:
                            break
                
                description = None
                desc_elem = soup.select_one('meta[property="og:description"]')
                if desc_elem:
                    description = desc_elem.get('content', '')
                
                image_url = None
                img_elem = soup.select_one('meta[property="og:image"]')
                if img_elem:
                    image_url = img_elem.get('content', '')
                
                if name:
                    return {
                        'name': name,
                        'description': description or '',
                        'image_url': image_url or '',
                        'game_url': url,
                        'game_api_url': game_api_url
                    }
        except Exception as e:
            print(f"Error extracting Poki iframe data: {e}")
    
    # For Game Distribution, try to extract from embedded JSON first
    if not is_poki and not is_gamepix:
        try:
            # Find the script containing __NEXT_DATA__
            next_data_script = soup.find('script', id='__NEXT_DATA__')
            if next_data_script:
                json_data = json.loads(next_data_script.string)
                game_data = json_data.get('props', {}).get('pageProps', {}).get('game', {})
                if game_data:
                    name = game_data.get('title', '')
                    description = game_data.get('description', '')
                    # Get the largest image URL available
                    assets = game_data.get('assets', [])
                    image_url = ''
                    max_width = 0
                    for asset in assets:
                        if asset.get('width', 0) > max_width:
                            image_url = f"https://img.gamedistribution.com/{asset['name']}"
                            max_width = asset['width']
                    
                    # Get game API URL
                    game_id = game_data.get('objectID', '')
                    if game_id:
                        game_api_url = f"https://html5.gamedistribution.com/{game_id}/"
                        
                        return {
                            'name': name,
                            'description': description,
                            'image_url': image_url,
                            'game_url': url,
                            'game_api_url': game_api_url
                        }
        except Exception as e:
            print(f"Error extracting Game Distribution data: {e}")
    
    # For GamePix, try to extract structured data
    if is_gamepix:
        try:
            # Extract game details from the structured content
            name = soup.select_one('h1')
            if name:
                name = name.text.strip()
            
            # Extract description from meta tags or game details section
            description = None
            desc_elem = soup.select_one('meta[name="description"]')
            if desc_elem:
                description = desc_elem.get('content', '').strip()
            
            # Extract image URL from meta tags or game preview
            image_url = None
            img_elem = soup.select_one('meta[property="og:image"]')
            if img_elem:
                image_url = img_elem.get('content', '')
            
            # Extract game API URL from the iframe or embed element
            game_api_url = None
            iframe = soup.select_one('iframe[src*="/embed/"]')
            if iframe:
                game_api_url = iframe.get('src', '')
            
            if name and (description or image_url):
                return {
                    'name': name,
                    'description': description or '',
                    'image_url': image_url or '',
                    'game_url': url,
                    'game_api_url': game_api_url or ''
                }
        except Exception as e:
            print(f"Error extracting GamePix data: {e}")
    
    # Fallback to traditional HTML scraping
    name = None
    name_selectors = [
        'meta[property="og:title"]',
        'meta[name="title"]'
    ]
    if is_poki:
        name_selectors.extend([
            'h1.game-name',
            'h1[class*="GameName"]',
            '.game-title',
            '[class*="title"]'
        ])
    elif is_gamepix:
        name_selectors.extend([
            'h1',
            '.game-title',
            '[class*="game-name"]'
        ])
    else:
        name_selectors.extend([
            'h1', 
            'h2', 
            '[class*="title"]',
            '[class*="game-title"]'
        ])
    
    for selector in name_selectors:
        elem = soup.select_one(selector)
        if elem:
            name = elem.get('content', '') or elem.text.strip()
            if name:
                break
    
    # Extract description with website-specific selectors
    description = None
    desc_selectors = [
        'meta[name="description"]',
        'meta[property="og:description"]'
    ]
    if is_poki:
        desc_selectors.extend([
            '.game-description',
            '[class*="Description"]',
            '.description'
        ])
    elif is_gamepix:
        desc_selectors.extend([
            '.game-description',
            '[class*="game-details"]',
            '[class*="description"]'
        ])
    else:
        desc_selectors.extend([
            '[class*="description"]',
            '[class*="game-description"]'
        ])
    
    for selector in desc_selectors:
        elem = soup.select_one(selector)
        if elem:
            description = elem.get('content', '') or elem.text.strip()
            if description:
                break
    
    # Extract image URL
    image_url = None
    img_selectors = [
        'meta[property="og:image"]',
        'meta[name="thumbnail"]'
    ]
    if is_poki:
        img_selectors.extend([
            '.game-image img',
            '[class*="GameImage"] img',
            '.thumbnail img'
        ])
    elif is_gamepix:
        img_selectors.extend([
            '.game-preview img',
            '.game-thumbnail img',
            '[class*="game-image"] img'
        ])
    else:
        img_selectors.extend([
            '[class*="game-image"] img',
            '[class*="thumbnail"] img',
            'img[src*="img.gamedistribution.com"]'
        ])
    
    for selector in img_selectors:
        elem = soup.select_one(selector)
        if elem:
            image_url = elem.get('content', '') or elem.get('src', '')
            if image_url:
                # Handle relative URLs
                if not image_url.startswith('http'):
                    if is_gamepix:
                        image_url = urljoin('https://www.gamepix.com', image_url)
                    else:
                        image_url = urljoin('https://gamedistribution.com', image_url)
                break
    
    # Extract game API URL
    game_api_url = None
    if is_poki:
        # Try to extract game ID from URL or meta tags
        game_id = None
        if '/g/' in url:
            game_id = url.split('/g/')[-1]
        else:
            meta_game_id = soup.find('meta', property='poki-game-id')
            if meta_game_id:
                game_id = meta_game_id.get('content', '')
        
        if game_id:
            game_api_url = f"https://game-cdn.poki.com/{game_id}/index.html"
    elif not is_gamepix:
        # Try to find game ID from URL or page content for Game Distribution
        game_id_match = re.search(r'/games/([a-f0-9]{32})', url) or re.search(r'game_id\s*:\s*["\']([a-f0-9]{32})["\']', html)
        if game_id_match:
            game_api_url = f"https://html5.gamedistribution.com/{game_id_match.group(1)}/"
    elif is_gamepix:
        # Try to find the game embed URL
        iframe = soup.select_one('iframe[src*="/embed/"]')
        if iframe:
            game_api_url = iframe.get('src', '')
    
    if name and (description or image_url):
        return {
            'name': name,
            'description': description or '',
            'image_url': image_url or '',
            'game_url': url,
            'game_api_url': game_api_url or ''
        }
    
    return None

def save_to_csv(games_data, filename):
    """Save games data to CSV file"""
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Name', 'URL', 'Description', 'Image URL', 'Game API URL', 'Website', 'Timestamp'])
            
            valid_games = 0
            for game in games_data:
                if isinstance(game, dict) and 'name' in game:
                    website = 'Poki' if 'poki.com' in game.get('game_url', '') else \
                            'GamePix' if 'gamepix.com' in game.get('game_url', '') else \
                            'Game Distribution'
                    
                    # Debug print for Poki games
                    if website == 'Poki':
                        print(f"\nPoki game found: {game.get('name', '')}")
                        print(f"Game API URL: {game.get('game_api_url', '')}")
                    
                    writer.writerow([
                        game.get('name', ''),
                        game.get('game_url', ''),
                        game.get('description', ''),
                        game.get('image_url', ''),
                        game.get('game_api_url', ''),
                        website,
                        time.strftime('%Y-%m-%d %H:%M:%S')
                    ])
                    valid_games += 1
            
            print(f"\nSuccessfully saved {valid_games} games to: {filename}")
            
    except Exception as e:
        print(f"\nError saving to {filename}: {e}")

async def main():
    """Main function to run the scraper"""
    websites = [
        'https://poki.com/en',
        'https://gamedistribution.com/games/',
        'https://www.gamepix.com/'
    ]
    
    all_games = []
    try:
        for website in websites:
            try:
                games = await scrape_website(website)
                if games:
                    # Filter out None values
                    games = [g for g in games if g is not None]
                    print(f"\nSuccessfully scraped {len(games)} games from {website}")
                    all_games.extend(games)
                else:
                    print(f"\nNo games found on {website}")
            except Exception as e:
                print(f"\nError scraping {website}: {e}")
                continue
        
        if all_games:
            # Count games by website
            poki_games = [g for g in all_games if g and isinstance(g, dict) and 'game_url' in g and 'poki.com' in g['game_url']]
            gd_games = [g for g in all_games if g and isinstance(g, dict) and 'game_url' in g and 'gamedistribution.com' in g['game_url']]
            gamepix_games = [g for g in all_games if g and isinstance(g, dict) and 'game_url' in g and 'gamepix.com' in g['game_url']]
            
            print(f"\nTotal valid games scraped: {len(all_games)}")
            print(f"- Poki: {len(poki_games)} games")
            print(f"- Game Distribution: {len(gd_games)} games")
            print(f"- GamePix: {len(gamepix_games)} games")
            
            # Save all games to CSV
            filename = 'games_data.csv'
            save_to_csv(all_games, filename)
        else:
            print("\nNo games were scraped from any website")
            
    except Exception as e:
        print(f"\nUnexpected error in main: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nScraping completed")

if __name__ == "__main__":
    asyncio.run(main())
