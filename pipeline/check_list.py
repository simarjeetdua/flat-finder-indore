import re, urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
urls = [
    "https://www.magicbricks.com/new-projects-Indore",
    "https://www.magicbricks.com/new-projects-Indore/page-2",
    "https://www.magicbricks.com/new-projects-Indore?page=2",
]
for u in urls:
    try:
        html = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "ignore")
    except Exception as e:
        print(u, "->", e)
        continue
    print(u, "-> OK, size", len(html))
    print("   totalCount:", re.findall(r'"totalCount":(\d+)', html)[:3])
    print("   psmName cards:", len(re.findall(r'"psmName":', html)), " pdpUrl:", len(re.findall(r'"pdpUrl":', html)))
    print("   SERVER_PRELOADED_STATE_:", "SERVER_PRELOADED_STATE_" in html)
    print("   sample project links:", list(dict.fromkeys(re.findall(r'https://www\.magicbricks\.com/[a-z0-9\-]+pdpid-[a-z0-9]+', html)))[:3])