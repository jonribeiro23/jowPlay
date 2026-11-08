import unittest

from ytdown.domain.urls import canonical_video_url, is_youtube_url, parse_url_list, video_id


class CanonicalVideoUrlTests(unittest.TestCase):
    """Igual ao `webpage_url` do yt-dlp, para achar duplicatas antes de baixar."""

    def test_every_link_form_gives_the_same_address(self):
        for url in (
            "https://youtu.be/jNQXAC9IVRw",
            "https://youtu.be/jNQXAC9IVRw?si=abc&t=10",
            "https://www.youtube.com/watch?v=jNQXAC9IVRw",
            "https://youtube.com/watch?feature=share&v=jNQXAC9IVRw&list=PL123",
            "https://m.youtube.com/watch?v=jNQXAC9IVRw",
            "https://music.youtube.com/watch?v=jNQXAC9IVRw",
            "https://www.youtube.com/shorts/jNQXAC9IVRw",
            "https://www.youtube.com/live/jNQXAC9IVRw?feature=share",
            "https://www.youtube.com/embed/jNQXAC9IVRw",
            "  https://youtu.be/jNQXAC9IVRw  ",
        ):
            with self.subTest(url):
                self.assertEqual(canonical_video_url(url), "https://www.youtube.com/watch?v=jNQXAC9IVRw")

    def test_links_without_a_video_have_no_address(self):
        for url in (
            "https://www.youtube.com/playlist?list=PL123",
            "https://www.youtube.com/@canal",
            "https://www.youtube.com/watch",
            "https://www.youtube.com/watch?v=curto",
            "https://youtu.be/",
            "https://example.com/watch?v=jNQXAC9IVRw",
            "não é url",
        ):
            with self.subTest(url):
                self.assertIsNone(canonical_video_url(url))
                self.assertIsNone(video_id(url))


class IsYoutubeUrlTests(unittest.TestCase):
    def test_accepts_youtube_urls(self):
        for url in (
            "https://www.youtube.com/watch?v=abc",
            "http://youtube.com/watch?v=abc",
            "https://m.youtube.com/watch?v=abc",
            "https://music.youtube.com/watch?v=abc",
            "  https://youtu.be/abc  ",
        ):
            self.assertTrue(is_youtube_url(url), url)

    def test_rejects_other_urls(self):
        for url in (
            "",
            "youtube.com/watch?v=abc",
            "ftp://youtube.com/watch?v=abc",
            "https://example.com/?u=youtube.com",
            "https://youtube.com.evil.example/watch?v=abc",
            "http://[invalid",
        ):
            self.assertFalse(is_youtube_url(url), url)


class ParseUrlListTests(unittest.TestCase):
    def test_reads_one_url_per_line_ignoring_blanks_and_spaces(self):
        text = "  https://youtu.be/a  \n\n\thttps://www.youtube.com/watch?v=b\n   \n"
        self.assertEqual(parse_url_list(text), (["https://youtu.be/a", "https://www.youtube.com/watch?v=b"], []))

    def test_repeated_urls_are_extracted_once(self):
        text = "https://youtu.be/a\nhttps://youtu.be/b\nhttps://youtu.be/a"
        self.assertEqual(parse_url_list(text), (["https://youtu.be/a", "https://youtu.be/b"], []))

    def test_reports_the_line_numbers_of_invalid_urls(self):
        text = "https://youtu.be/a\nisto não é url\n\nhttps://example.com/v"
        self.assertEqual(parse_url_list(text), (["https://youtu.be/a"], [2, 4]))

    def test_empty_text(self):
        self.assertEqual(parse_url_list("  \n \n"), ([], []))


if __name__ == "__main__":
    unittest.main()
