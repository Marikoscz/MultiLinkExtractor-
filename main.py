import os
import re
import ctypes
import asyncio
import platform
from urllib.parse import urlparse, urljoin
import time
import aiohttp
from bs4 import BeautifulSoup
import json
from datetime import datetime
from colorama import init, Fore, Style
from urllib.parse import unquote
from curl_cffi.requests import AsyncSession

init(autoreset=True)  # Initialize colorama

def set_console_title(title):
    system = platform.system()
    if system == "Windows":
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    else:
        print(f"\33]0;{title}\a", end="", flush=True)

async def get_fuckingfast_link(session, download_url):

    download_url = download_url.strip()
    if not download_url:
        return None

    try:
        async with AsyncSession(impersonate="chrome") as cf_session:
            response = await cf_session.get(download_url, timeout=15)
            
            if response.status_code != 200:
                return None
                
            html = response.text
            
            match = re.search(r'window\.open\("(https://dl\.fuckingfast\.co/dl/[^"]+)"\)', html)
            if match:
                return match.group(1)
                
            htmx_match = re.search(r'hx-(?:post|get)="([^"]+)"', html)
            
            if not htmx_match:
                file_id_match = re.search(r'fuckingfast\.co/(?:f/)?([a-zA-Z0-9]+)', download_url)
                if file_id_match:
                    endpoint_path = f"/f/{file_id_match.group(1)}/go"
                else:
                    endpoint_path = None
            else:
                endpoint_path = htmx_match.group(1)

            if endpoint_path:
                endpoint_url = urljoin(download_url, endpoint_path)
                headers = {
                    "HX-Request": "true",
                    "HX-Current-URL": download_url,
                    "Referer": download_url,
                }
                
                is_get = "hx-get" in (htmx_match.group(0).lower() if htmx_match else "")
                
                if is_get:
                    api_resp = await cf_session.get(endpoint_url, headers=headers, timeout=15, allow_redirects=False)
                else:
                    api_resp = await cf_session.post(endpoint_url, headers=headers, timeout=15, allow_redirects=False)

                direct_link = api_resp.headers.get("hx-redirect") or api_resp.headers.get("HX-Redirect") or api_resp.headers.get("location") or api_resp.headers.get("Location")
                
                if not direct_link and api_resp.text:
                    dl_match = re.search(r'(https://dl\.fuckingfast\.co/dl/[^"\s\'<>]+)', api_resp.text)
                    if dl_match:
                        direct_link = dl_match.group(1)
                
                if direct_link:
                    return direct_link
                    
    except Exception as e:
        pass
        
    return None

async def get_datanodes_link(session, download_url):
    download_url = download_url.strip()
    if not download_url:
        return None

    def normalize_link(url, base_url):
        if not url:
            return None
        url = unquote(url.strip().strip("'\""))
        url = url.replace("\\/", "/")
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("/"):
            return urljoin(base_url, url)
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return None

    def extract_link_from_dict(data, base_url):
        if not isinstance(data, dict):
            return None
        candidate_keys = [
            "url",
            "link",
            "download_url",
            "download",
            "redirect",
            "location",
            "href",
            "file",
            "result",
        ]
        for key in candidate_keys:
            value = data.get(key)
            if isinstance(value, str):
                candidate = normalize_link(value, base_url)
                if candidate and "datanodes.to" not in candidate.lower():
                    return candidate
            elif isinstance(value, dict):
                nested = extract_link_from_dict(value, base_url)
                if nested:
                    return nested
        return None

    def extract_link_from_text(text, base_url):
        if not text:
            return None
        patterns = [
            r'"url"\s*:\s*"([^"]+)"',
            r'"(?:link|download_url|href|redirect|location)"\s*:\s*"([^"]+)"',
            r"window\.location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]",
            r"(?:window\.)?open\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
            r"href=['\"]([^'\"]+)['\"][^>]*>\s*(?:Download|Click here|Continue)\s*<",
            r"href=['\"]([^'\"]+)['\"][^>]*>\s*(?:Download|Click here)\s*<",
            r"(https?://[^\s\"'<>]+)",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                candidate = normalize_link(match, base_url)
                if candidate and not candidate.lower().startswith("javascript:"):
                    if "datanodes.to" not in candidate.lower():
                        return candidate

        try:
            json_match = re.search(r"(?s)\{.*\}", text)
            if json_match:
                data = json.loads(json_match.group(0))
                candidate = extract_link_from_dict(data, base_url)
                if candidate:
                    return candidate
        except Exception:
            pass

        return None

    parsed_url = urlparse(download_url)
    path_segments = [segment for segment in parsed_url.path.split("/") if segment]
    fallback_file_code = path_segments[0] if path_segments else ""

    def build_headers(origin, referer):
        return {
            "Accept": "text/html,application/json,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": origin,
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
        }

    def extract_from_response(response, base_url):
        location = (
            response.headers.get("location")
            or response.headers.get("Location")
            or response.headers.get("hx-redirect")
            or response.headers.get("HX-Redirect")
        )
        direct = normalize_link(location, base_url)
        if direct and "datanodes.to" not in direct.lower():
            return direct

        body_link = extract_link_from_text(response.text, base_url)
        if body_link:
            return body_link

        try:
            data = response.json()
            dict_link = extract_link_from_dict(data, base_url)
            if dict_link:
                return dict_link
        except Exception:
            pass
        return None

    try:
        async with AsyncSession(impersonate="chrome") as cf_session:
            page_response = await cf_session.get(download_url, timeout=20)
            if page_response.status_code != 200:
                return None

            html = page_response.text
            immediate_link = extract_link_from_text(html, download_url)
            if immediate_link:
                return immediate_link

            soup = BeautifulSoup(html, "html.parser")
            form = None
            for candidate_form in soup.find_all("form"):
                names = {i.get("name", "").lower() for i in candidate_form.find_all("input")}
                if "op" in names or "method_free" in names or "id" in names:
                    form = candidate_form
                    break
            if form is None:
                form = soup.find("form")
            if not form:
                return None

            payload = {}
            for input_field in form.find_all("input"):
                name = input_field.get("name")
                if name:
                    payload[name] = input_field.get("value", "")

            payload.setdefault("op", "download2")
            payload.setdefault("id", fallback_file_code)
            payload.setdefault("rand", "")
            payload.setdefault("referer", "")
            payload.setdefault("method_free", "Free Download")
            payload.setdefault("method_premium", "")
            payload.setdefault("__dl", "1")

            wait_match = re.search(r"var\s+(?:seconds|sec)\s*=\s*(\d+)", html, flags=re.IGNORECASE)
            if wait_match:
                wait_seconds = min(int(wait_match.group(1)), 15)
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds + 1)

            form_action = form.get("action") or download_url
            form_url = urljoin(download_url, form_action)
            origin = f"{parsed_url.scheme}://{parsed_url.netloc}"

            method_free_values = [
                payload.get("method_free") or "Free Download",
                "Free Download",
                "Free Download >>",
                "Slow Download",
                "",
            ]
            seen = set()
            for method_free_value in method_free_values:
                if method_free_value in seen:
                    continue
                seen.add(method_free_value)
                payload_try = dict(payload)
                payload_try["method_free"] = method_free_value

                for endpoint in [form_url, download_url]:
                    response = await cf_session.post(
                        endpoint,
                        data=payload_try,
                        headers=build_headers(origin, download_url),
                        timeout=20,
                        allow_redirects=False,
                    )
                    extracted = extract_from_response(response, download_url)
                    if extracted:
                        return extracted

                    if response.status_code in (301, 302, 303, 307, 308):
                        redirected = normalize_link(response.headers.get("Location"), download_url)
                        if redirected and "datanodes.to" not in redirected.lower():
                            return redirected
    except Exception:
        return None

    return None

async def process_links(urls):
    async with aiohttp.ClientSession() as session:
        results = []
        total_urls = len(urls)
        successful = 0
        failed_urls = []
        
        start_time = time.time()
        
        print(f"{Fore.CYAN}[*] Processing {total_urls} URLs...")
        print(f"{Fore.YELLOW}╔{'═' * 70}╗")
        
        for index, url in enumerate(urls):
            url = url.strip()
            if url:
                parsed_url = urlparse(url)
                download_link = None
                service_name = ""
                
                if "fuckingfast.co" in parsed_url.netloc:
                    service_name = "Fuckingfast"
                    progress = f"[{index + 1}/{total_urls}] Processing {service_name}"
                    set_console_title(f"Fuckingfast Link Generator - {index + 1}/{total_urls}")
                    print(f"{Fore.YELLOW}║ {Fore.CYAN}{progress:<68}{Fore.YELLOW} ║")
                    download_link = await get_fuckingfast_link(session, url)
                elif "datanodes.to" in parsed_url.netloc:
                    service_name = "Datanodes"
                    progress = f"[{index + 1}/{total_urls}] Processing {service_name}"
                    print(f"{Fore.YELLOW}║ {Fore.CYAN}{progress:<68}{Fore.YELLOW} ║")
                    set_console_title(f"Datanodes Link Generator - {index + 1}/{total_urls}")
                    download_link = await get_datanodes_link(session, url)
                
                if download_link:
                    successful += 1
                    status_msg = f"✓ {service_name} link extracted"
                    print(f"{Fore.YELLOW}║ {Fore.GREEN}{status_msg:<68}{Fore.YELLOW} ║")
                else:
                    failed_urls.append(url)
                    status_msg = f"✗ Failed to extract {service_name} link"
                    print(f"{Fore.YELLOW}║ {Fore.RED}{status_msg:<68}{Fore.YELLOW} ║")
                
                results.append({
                    "original_url": url,
                    "download_link": download_link,
                    "success": download_link is not None,
                    "service": service_name
                })
        
        print(f"{Fore.YELLOW}╚{'═' * 70}╝")
        elapsed_time = time.time() - start_time
        
        return {
            "results": results,
            "stats": {
                "total": total_urls,
                "successful": successful,
                "failed": total_urls - successful,
                "success_rate": (successful / total_urls * 100) if total_urls > 0 else 0,
                "elapsed_time": elapsed_time,
                "failed_urls": failed_urls
            }
        }

if __name__ == "__main__":
    if not os.path.exists("links.txt"):
        with open("links.txt", "w") as file:
            print(f"{Fore.RED}[!] Created empty links.txt file. Please add URLs and run again.")
            exit()
            
    with open("links.txt", "r") as file:
        urls = [url.strip() for url in file.readlines() if url.strip()]
    
    if not urls:
        print(f"{Fore.RED}[!] No URLs found in links.txt")
        exit()
    
    print(f"{Fore.CYAN}[*] Starting processing of {len(urls)} URLs...")
    result_data = asyncio.run(process_links(urls))
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    with open(f"outputs_links_{timestamp}.txt", "w", encoding="utf-8") as output_file:
        for item in result_data["results"]:
            if item["download_link"]:
                output_file.write(f"{item['download_link']}\n")
    
    stats = result_data["stats"]
    
    print("\n")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'╔' + '═' * 48 + '╗'}")
    print(f"{Fore.CYAN}{Style.BRIGHT}║{' ' * 18}SUMMARY REPORT{' ' * 16}║")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'╠' + '═' * 48 + '╣'}")
    
    success_color = Fore.GREEN if stats['success_rate'] > 80 else Fore.YELLOW if stats['success_rate'] > 50 else Fore.RED
    
    print(f"{Fore.CYAN}{Style.BRIGHT}║ {Fore.WHITE}Total URLs processed:{' ' * 16}{stats['total']:<10}{Fore.CYAN}{Style.BRIGHT}║")
    print(f"{Fore.CYAN}{Style.BRIGHT}║ {Fore.GREEN}Successful extractions:{' ' * 14}{stats['successful']:<10}{Fore.CYAN}{Style.BRIGHT}║")
    print(f"{Fore.CYAN}{Style.BRIGHT}║ {Fore.RED}Failed extractions:{' ' * 18}{stats['failed']:<10}{Fore.CYAN}{Style.BRIGHT}║")
    print(f"{Fore.CYAN}{Style.BRIGHT}║ {success_color}Success rate:{' ' * 24}{stats['success_rate']:.2f}%{' ' * 3}{Fore.CYAN}{Style.BRIGHT}║")
    print(f"{Fore.CYAN}{Style.BRIGHT}║ {Fore.WHITE}Time elapsed:{' ' * 24}{stats['elapsed_time']:.2f}s{' ' * 5}{Fore.CYAN}{Style.BRIGHT}║")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'╚' + '═' * 48 + '╝'}")
    
    if stats['failed'] > 0:
        print(f"\n{Fore.RED}{Style.BRIGHT}FAILED URLS:")
        print(f"{Fore.RED}{'─' * 50}")
        for i, failed_url in enumerate(stats['failed_urls'], 1):
            print(f"{Fore.RED}{i}. {failed_url}")
    
    print(f"\n{Fore.GREEN}[*] Download links saved to {Fore.YELLOW}outputs_links_{timestamp}.txt")
    
    # Service-specific stats
    service_stats = {}
    for result in result_data["results"]:
        service = result["service"]
        if service not in service_stats:
            service_stats[service] = {"total": 0, "success": 0, "failed": 0}
        service_stats[service]["total"] += 1
        if result["success"]:
            service_stats[service]["success"] += 1
        else:
            service_stats[service]["failed"] += 1
    
    if service_stats:
        print(f"\n{Fore.CYAN}{Style.BRIGHT}SERVICE-SPECIFIC STATS:")
        print(f"{Fore.CYAN}{'─' * 50}")
        for service, stats in service_stats.items():
            success_rate = (stats["success"] / stats["total"]) * 100 if stats["total"] > 0 else 0
            status_color = Fore.GREEN if success_rate > 80 else Fore.YELLOW if success_rate > 50 else Fore.RED
            print(f"{Fore.WHITE}{service}: {status_color}{stats['success']}/{stats['total']} ({success_rate:.2f}%)")
