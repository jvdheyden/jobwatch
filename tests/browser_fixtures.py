"""Small Playwright boundary double. Production selectors/parsers still run.

Fixtures contain raw DOM observations (text/attributes/scripts), never Candidates.
Unexpected selectors fail loudly instead of making a broken selector look empty.
"""
from types import SimpleNamespace


class Locator:
    def __init__(self, elements, page):
        self.elements, self.page = elements, page

    @property
    def first(self):
        return self.nth(0)

    def nth(self, index):
        return Locator(self.elements[index:index + 1], self.page)

    def count(self):
        return len(self.elements)

    def inner_text(self, **kwargs):
        return self.elements[0].get('text', '')

    def all_inner_texts(self):
        return [e.get('text', '') for e in self.elements]

    def get_attribute(self, key):
        return self.elements[0].get(key)

    def locator(self, selector):
        return Locator(self.elements[0].get('children', {}).get(selector, []), self.page)

    def evaluate(self, expression):
        element = self.elements[0]
        if 'disabled' in expression:
            return element.get('disabled', False)
        return element.get('card_text', element.get('text', ''))

    def evaluate_all(self, expression):
        assert not self.elements, "Only absent cookie overlays are recorded"

    def click(self, **kwargs):
        self.page.index = min(self.page.index + 1, len(self.page.pages) - 1)

    def scroll_into_view_if_needed(self, **kwargs):
        pass


class Page:
    def __init__(self, pages, error=None):
        self.pages, self.index, self.error = pages, 0, error
        self.visited = []

    def goto(self, url, **kwargs):
        self.visited.append(url)
        if self.error:
            raise self.error
        self.index = 1 if ('page=2' in url or 'from=20' in url) and len(self.pages) > 1 else 0

    def locator(self, selector):
        selectors = self.pages[self.index]
        # Cookie controls are optional UI capabilities.
        if selector.startswith('#onetrust-'):
            return Locator([], self)
        assert selector in selectors, f'Unrecorded browser selector: {selector}'
        return Locator(selectors[selector], self)

    def get_by_role(self, role, **kwargs):
        return self.locator(f"{role}:{kwargs.get('name', '')}")

    def close(self):
        pass

    def title(self):
        return self.pages[self.index].get('title', 'Careers')

    def wait_for_timeout(self, milliseconds):
        pass

    def wait_for_function(self, *args, **kwargs):
        pass

    def evaluate(self, expression):
        pass


class Browser:
    def __init__(self, page):
        self.page = page
        page.context = SimpleNamespace(browser=self)
        self.closed = False

    def new_page(self, **kwargs):
        return self.page

    def close(self):
        self.closed = True


class Playwright:
    def __init__(self, browser):
        self.chromium = SimpleNamespace(launch=lambda **kwargs: browser)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def install_browser(monkeypatch, pages, error=None):
    from discover.sources import browser as provider
    browser = Browser(Page(pages, error))
    monkeypatch.setattr(provider, 'load_sync_playwright', lambda: lambda: Playwright(browser))
    return browser
