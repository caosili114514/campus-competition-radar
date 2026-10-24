import unittest

from collector.extractors import extract_item
from collector.parsers import (
    HtmlListParser,
    JsonFeedParser,
    RssAtomParser,
    extract_main_content,
)

SOURCE = {
    "id": "fixture",
    "name": "离线 fixture 来源",
    "list_url": "https://example.edu/list",
    "source_type": "fixture",
}


class ParserTests(unittest.TestCase):
    def test_html_list_parser(self):
        html = """
        <ul>
          <li><a href="/notice/1">关于举办2026年全国大学生数学建模竞赛的通知</a>
              <time datetime="2026-10-20"></time><p>列表摘要</p></li>
          <li><a href="/notice/2">程序设计大赛报名通知</a></li>
        </ul>
        """
        items = HtmlListParser().parse(html, SOURCE, base_url="https://example.edu/list")
        self.assertGreaterEqual(len(items), 2)
        self.assertEqual(items[0]["url"], "https://example.edu/notice/1")
        self.assertEqual(items[0]["published_at"], "2026-10-20T00:00:00+08:00")

    def test_rss_and_atom_parser(self):
        rss = """<rss><channel><item><title>测试大赛</title>
        <link>https://example.edu/a</link><pubDate>Sat, 24 Oct 2026 20:56:20 +0800</pubDate>
        <description>报名截止：2026年11月1日</description></item></channel></rss>"""
        items = RssAtomParser().parse(rss, SOURCE)
        self.assertEqual(items[0]["title"], "测试大赛")
        self.assertEqual(items[0]["published_at"], "2026-10-24T20:56:20+08:00")
        atom = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>Atom 竞赛</title><link href="https://example.edu/atom"/>
        <updated>2026-10-24T12:56:20Z</updated><summary>摘要</summary></entry></feed>"""
        atom_items = RssAtomParser().parse(atom, SOURCE)
        self.assertEqual(atom_items[0]["url"], "https://example.edu/atom")
        self.assertEqual(atom_items[0]["published_at"], "2026-10-24T20:56:20+08:00")

    def test_json_feed_parser(self):
        payload = '{"items":[{"title":"JSON 竞赛","url":"/n/1","published_at":"2026-10-24","content":"正文"}]}'
        items = JsonFeedParser().parse(payload, SOURCE, base_url="https://example.edu/list")
        self.assertEqual(items[0]["url"], "https://example.edu/n/1")
        self.assertEqual(items[0]["published_at"], "2026-10-24T00:00:00+08:00")

    def test_form_wrapped_main_content_and_body_header_time(self):
        html = """<html><body><nav>首页</nav><form name="_newscontent_fromname">
        <div class="content"><div class="content-title"><h3>计算机设计大赛通知</h3></div>
        <i>发布者：教务处&nbsp;&nbsp;时间：2026-09-14&nbsp;&nbsp;浏览：1</i>
        <div id="vsb_content" class="content-con"><div class="v_news_content">
        <p>报名时间：2026年10月1日至2026年10月20日。</p>
        <p>作品要求：提交设计说明。</p></div></div></div></form>
        <footer>版权</footer></body></html>"""
        page = extract_main_content(html)
        self.assertEqual(page["content_source"], "main")
        self.assertEqual(page["published_at"], "2026-09-14T00:00:00+08:00")
        self.assertIn("报名时间", page["content"])
        self.assertNotIn("版权", page["content"])

    def test_detail_main_content_excludes_navigation_and_scripts(self):
        html = """<html><head><meta property="og:title" content="详情标题">
        <meta property="article:published_time" content="2026-10-20T10:00:00+08:00"></head>
        <body><nav>首页 导航 登录</nav><header>页头</header>
        <div class="article-content"><h1>详情标题</h1>
        <p>主办单位：测试大学。</p><p>报名时间：2026年11月1日至2026年11月30日。</p>
        <p>每队1-3人。作品要求：提交设计说明。</p></div>
        <script>alert('不应出现')</script><footer>版权</footer></body></html>"""
        page = extract_main_content(html)
        self.assertEqual(page["title"], "详情标题")
        self.assertIn("主办单位", page["content"])
        self.assertNotIn("导航", page["content"])
        self.assertNotIn("不应出现", page["content"])
        self.assertEqual(page["published_at"], "2026-10-20T10:00:00+08:00")
        self.assertEqual(page["content_source"], "main")


class ExtractorTests(unittest.TestCase):
    def test_fields_and_explicit_registration_url(self):
        item = {
            "title": "关于举办2026年全国大学生数学建模竞赛的通知",
            "url": "https://example.edu/notice/1",
            "content": "主办单位：中国工业与应用数学学会。赛事级别：国家级。参赛对象：全日制在校大学生。每队1-3人。"
                       "报名时间：2026年3月1日至2026年4月30日。比赛时间：2026年5月1日至5月3日。"
                       "作品要求：提交论文与代码。报名入口：https://example.edu/signup",
            "published_at": "2026-10-20T09:00:00+08:00",
        }
        record = extract_item(item, SOURCE, now="2026-10-24T20:56:20+08:00")
        self.assertEqual(record["organizer"], "中国工业与应用数学学会")
        self.assertEqual(record["competition_level"], "国家级")
        self.assertEqual(record["team_size"], "1-3人")
        self.assertEqual(record["registration_start"], "2026-03-01T00:00:00+08:00")
        self.assertEqual(record["registration_deadline"], "2026-04-30T23:59:59+08:00")
        self.assertEqual(record["registration_url"], "https://example.edu/signup")
        self.assertEqual(record["source_url"], "https://example.edu/notice/1")
        self.assertEqual(record["source_list_url"], "https://example.edu/list")
        self.assertEqual(record["verification_status"], "pending")
        self.assertEqual(record["is_demo"], False)

    def test_level_is_not_guessed_from_college_word(self):
        record = extract_item({
            "title": "某学院程序设计竞赛通知",
            "url": "https://example.edu/notice/level",
            "content": "某学院发布竞赛通知，未写明赛事级别。",
        }, SOURCE, now="2026-10-24T20:56:20+08:00")
        self.assertIsNone(record["competition_level"])

    def test_unknown_fields_are_null_and_registration_url_not_guessed(self):
        item = {
            "title": "一条信息很少的竞赛通知",
            "url": "https://example.edu/notice/only",
            "content": "详情正文提及一个普通页面 https://example.edu/about，但没有明确报名入口。",
        }
        record = extract_item(item, SOURCE, now="2026-10-24T20:56:20+08:00")
        self.assertIsNone(record["organizer"])
        self.assertIsNone(record["registration_deadline"])
        self.assertIsNone(record["registration_url"])
        self.assertIn("registration_url", record["missing_fields"])
        self.assertIn("organizer", record["missing_fields"])


if __name__ == "__main__":
    unittest.main()
