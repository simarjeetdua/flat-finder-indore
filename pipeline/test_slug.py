import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
slugs = ["gurgaon", "indore", "indore-city", "indore-madhya-pradesh", "indore-region"]
for s in slugs:
    url = f"https://www.magicbricks.com/residential-projects-in-{s}-nprid/page-1"
    try:
        code = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).status
    except Exception as e:
        code = e
    print(s, "->", code)