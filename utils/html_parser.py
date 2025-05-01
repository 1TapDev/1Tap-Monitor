#!/usr/bin/env python3
"""
HTML Parser Utilities
Functions to help parse HTML from retail websites and extract product information.
"""

import re
import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("HTMLParser")

# Try to import BeautifulSoup
try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("BeautifulSoup not available, falling back to regex-based parsing")


def extract_pids_from_html(html: str, base_url: str = "") -> List[Dict[str, str]]:
    """
    Extract product IDs and basic info from HTML using either BeautifulSoup or regex

    Args:
        html: HTML content to parse
        base_url: Base URL for resolving relative URLs

    Returns:
        List of dictionaries with product information
    """
    products = []

    # Use BeautifulSoup if available
    if BS4_AVAILABLE:
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Find all product items in the search results
            product_items = soup.select('.search-result-item')

            for item in product_items:
                product = {}

                # Extract PID from various possible locations
                # From wishlist link
                wishlist_link = item.select_one('.search-add-to-wishlist a')
                if wishlist_link and 'href' in wishlist_link.attrs:
                    pid_match = re.search(r'pid=([A-Za-z0-9]+)', wishlist_link['href'])
                    if pid_match:
                        product['pid'] = pid_match.group(1)

                # From cart link
                cart_link = item.select_one('.addToCartLink')
                if cart_link and 'href' in cart_link.attrs:
                    pid_match = re.search(r'buyit=([A-Za-z0-9]+)', cart_link['href'])
                    if pid_match:
                        product['pid'] = pid_match.group(1)

                # From product link
                product_link = item.select_one('.search-item-title a')
                if product_link and 'href' in product_link.attrs:
                    product['url'] = urljoin(base_url, product_link['href'])
                    product['title'] = product_link.get_text().strip()

                    # Extract PID from URL if not found yet
                    if 'pid' not in product:
                        pid_match = re.search(r'/([A-Za-z0-9]+)$', product['url'])
                        if pid_match:
                            product['pid'] = pid_match.group(1)

                # Extract image
                img_tag = item.select_one('.imageContainer img')
                if img_tag and 'src' in img_tag.attrs:
                    product['image'] = urljoin(base_url, img_tag['src'])

                # Extract price
                price_tag = item.select_one('.our-price')
                if price_tag:
                    product['price'] = price_tag.get_text().strip().replace('$', '').strip()

                # Extract author
                author_tag = item.select_one('.search-item-author')
                if author_tag:
                    product['author'] = author_tag.get_text().strip().replace('by ', '')

                # Extract availability
                availability_tag = item.select_one('.availability_search_results')
                if availability_tag:
                    availability_text = availability_tag.get_text().strip()
                    product['online_availability'] = availability_text.replace('Online: ', '')

                store_availability_tag = item.select_one('.searchItemAvailability')
                if store_availability_tag:
                    store_availability_text = store_availability_tag.get_text().strip()
                    product['store_availability'] = store_availability_text.replace('My Store: ', '')

                # Only add product if we have a PID
                if 'pid' in product:
                    products.append(product)

            logger.info(f"Extracted {len(products)} products using BeautifulSoup")

        except Exception as e:
            logger.error(f"Error parsing HTML with BeautifulSoup: {str(e)}")
            # Fall back to regex parsing
            return extract_pids_with_regex(html, base_url)
    else:
        # Fall back to regex parsing
        return extract_pids_with_regex(html, base_url)

    return products


def extract_pids_with_regex(html: str, base_url: str = "") -> List[Dict[str, str]]:
    """
    Extract product IDs from HTML using regex patterns (fallback method)

    Args:
        html: HTML content to parse
        base_url: Base URL for resolving relative URLs

    Returns:
        List of dictionaries with product information
    """
    products = []

    try:
        # Extract product IDs from various patterns

        # From wishlist links
        wishlist_patterns = [
            r'wishlist\?pid=([A-Za-z0-9]+)',
            r'action=wadd&pid=([A-Za-z0-9]+)'
        ]

        for pattern in wishlist_patterns:
            for match in re.finditer(pattern, html):
                pid = match.group(1)
                # Check if this PID is already added
                if not any(p.get('pid') == pid for p in products):
                    products.append({'pid': pid})

        # From cart links
        cart_patterns = [
            r'action=add&buyit=([A-Za-z0-9]+)',
            r'addtocart\([\'"].*?buyit=([A-Za-z0-9]+)'
        ]

        for pattern in cart_patterns:
            for match in re.finditer(pattern, html):
                pid = match.group(1)
                # Check if this PID is already added
                existing_product = next((p for p in products if p.get('pid') == pid), None)
                if existing_product is None:
                    products.append({'pid': pid})

        # Try to extract more information for each product
        # This is less reliable with regex than with BeautifulSoup

        # Extract product blocks
        product_blocks = re.finditer(r'<div class="search-result-item"[^>]*>(.*?)</div></div></div>', html, re.DOTALL)

        for block_match in product_blocks:
            block = block_match.group(1)

            # Extract PID
            pid_match = re.search(r'pid=([A-Za-z0-9]+)', block)
            if not pid_match:
                pid_match = re.search(r'buyit=([A-Za-z0-9]+)', block)

            if pid_match:
                pid = pid_match.group(1)

                # Check if this PID is already added
                existing_product = next((p for p in products if p.get('pid') == pid), None)

                if existing_product is None:
                    product = {'pid': pid}
                    products.append(product)
                else:
                    product = existing_product

                # Extract title
                title_match = re.search(r'<div class="search-item-title">\s*<a[^>]*>(.*?)</a>', block, re.DOTALL)
                if title_match:
                    product['title'] = title_match.group(1).strip()

                # Extract URL
                url_match = re.search(r'<a href="([^"]+)"[^>]*>.*?</a>', block)
                if url_match:
                    product['url'] = urljoin(base_url, url_match.group(1))

                # Extract price
                price_match = re.search(r'<span class="our-price">\s*\$([\d\.]+)', block)
                if price_match:
                    product['price'] = price_match.group(1)

        logger.info(f"Extracted {len(products)} products using regex")

    except Exception as e:
        logger.error(f"Error parsing HTML with regex: {str(e)}")

    return products


def parse_product_details(html: str, base_url: str = "") -> Dict[str, Any]:
    """
    Parse detailed product information from a product page

    Args:
        html: HTML content to parse
        base_url: Base URL for resolving relative URLs

    Returns:
        Dictionary with product details
    """
    product = {}

    # Use BeautifulSoup if available
    if BS4_AVAILABLE:
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Extract title
            title_tag = soup.select_one('h1.title_thing')
            if title_tag:
                product['title'] = title_tag.get_text().strip()

            # Extract author
            author_tag = soup.select_one('div.author')
            if author_tag:
                product['author'] = author_tag.get_text().strip().replace('by ', '')

            # Extract price
            price_tag = soup.select_one('span#our_price')
            if price_tag:
                product['price'] = price_tag.get_text().strip().replace('$', '').strip()

            # Extract image URL
            img_tag = soup.select_one('#feature_image img')
            if img_tag and 'src' in img_tag.attrs:
                product['image'] = urljoin(base_url, img_tag['src'])

            # Extract ISBN
            isbn_tag = soup.select_one('div.product-isbn')
            if isbn_tag:
                isbn_text = isbn_tag.get_text().strip()
                isbn_match = re.search(r'ISBN-13:\s*(\d+)', isbn_text)
                if isbn_match:
                    product['isbn'] = isbn_match.group(1)

            # Extract publication date
            pub_date_tag = soup.select_one('div.product-pubdate')
            if pub_date_tag:
                pub_date_text = pub_date_tag.get_text().strip()
                pub_date_match = re.search(r'Publish Date:\s*([\w\s,]+)', pub_date_text)
                if pub_date_match:
                    product['pub_date'] = pub_date_match.group(1).strip()

            # Extract availability
            availability_tag = soup.select_one('div.product-inventory')
            if availability_tag:
                product['availability'] = availability_tag.get_text().strip()

            logger.info(f"Parsed product details for {product.get('title', 'Unknown Product')}")

        except Exception as e:
            logger.error(f"Error parsing product details with BeautifulSoup: {str(e)}")
    else:
        # Fallback to regex parsing for product details
        try:
            # Extract title
            title_match = re.search(r'<h1[^>]*class="title_thing"[^>]*>(.*?)</h1>', html, re.DOTALL)
            if title_match:
                product['title'] = title_match.group(1).strip()

            # Extract author
            author_match = re.search(r'<div[^>]*class="author"[^>]*>(.*?)</div>', html, re.DOTALL)
            if author_match:
                product['author'] = author_match.group(1).strip().replace('by ', '')

            # Extract price
            price_match = re.search(r'<span[^>]*id="our_price"[^>]*>\s*\$([\d\.]+)', html)
            if price_match:
                product['price'] = price_match.group(1)

            # Extract image URL
            img_match = re.search(r'<img[^>]*id="feature_image"[^>]*src="([^"]+)"', html)
            if img_match:
                product['image'] = urljoin(base_url, img_match.group(1))

            logger.info(f"Parsed product details for {product.get('title', 'Unknown Product')} using regex")

        except Exception as e:
            logger.error(f"Error parsing product details with regex: {str(e)}")

    return product


def extract_json_from_html(html: str,
                           pattern: str = r'<script[^>]*type="application/json"[^>]*>(.*?)</script>') -> Dict:
    """
    Extract JSON data embedded in HTML

    Args:
        html: HTML content to parse
        pattern: Regex pattern to find JSON data

    Returns:
        Parsed JSON data as dictionary
    """
    try:
        json_match = re.search(pattern, html, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            return json.loads(json_str)
    except Exception as e:
        logger.error(f"Error extracting JSON from HTML: {str(e)}")

    return {}


if __name__ == "__main__":
    # Configure logging for standalone testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Test HTML snippet
    test_html = """
    <div class="search-result-item" data-cnstrc-item-id="820650412493" data-cnstrc-item-name="Pokemon Trading Card Game">
        <div class="search-tagged-image">
            <div class="imageContainer">
                <a href="https://www.booksamillion.com/p/Pokemon-Trading-Card-Game/Pokemon-International/F820650412493" title="Pokemon Trading Card Game">
                    <img src="https://covers.booksamillion.com/covers/gift/8/20/650/412/820650412493-1.jpg" alt="Pokemon Trading Card Game|The Pokemon Company International">
                </a>
            </div>
        </div>
        <div class="search-item-meta">
            <div class="alignWrap">
                <div class="search-item-title">
                    <a href="https://www.booksamillion.com/p/Pokemon-Trading-Card-Game/Pokemon-International/F820650412493" title="Pokemon Trading Card Game">Pokemon Trading Card Game</a>
                </div>
                <div class="productInfoText"></div>
                <div class="search-item-author">by <a href="search2?query=The+Pokemon+Company+International&filters[brand]=The+Pokemon+Company+International" title="The Pokemon Company International">The Pokemon Company International</a></div>
            </div>
        </div>
        <div class="flexBottomContent">
            <div class="availability_search_results" title="Sorry: This item is not currently available.">Online: <span class="stockRed">Unavailable</span></div>
            <div class="searchItemAvailability" style="font-size: 11px;" title="Out of Stock">My Store: <span class="stockRed">Out of Stock</span></div>
            <div class="priceBlock"><span class="our-price">$4.99</span></div>
            <div class="productPID">820650412493</div>
            <div class="search-buttons">
                <div class="search-add-to-wishlist" data-cnstrc-btn="add_to_wishlist"><a href="https://www.booksamillion.com/wishlist?pid=F820650412493&sort_by=release_date&query=The+Pokemon+Company+International&action=wadd&filters%5Bbrand%5D=The+Pokemon+Company+International" title="Add &quot;Pokemon Trading Card Game&quot; to your Wishlist"><i class="material-icons"></i></a></div>
                <div class="addToCartBTN addToCartUnvail"><div class="aTcBTNtext"></div></div>
            </div>
        </div>
    </div>
    """

    # Test the extraction
    products = extract_pids_from_html(test_html, "https://www.booksamillion.com")

    # Print results
    print("Extracted products:")
    for product in products:
        print(json.dumps(product, indent=2))