"""
Slice 10 - PWA / Mobile QA Tests
Tests manifest.json, service worker, template meta tags, and mobile CSS loading.
"""
import os
import json
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestManifestJSON:
    """PWA manifest.json structural tests."""

    @pytest.fixture
    def manifest(self):
        manifest_path = os.path.join(BASE_DIR, 'manifest.json')
        with open(manifest_path, 'r') as f:
            return json.load(f)

    def test_file_exists(self):
        assert os.path.exists(os.path.join(BASE_DIR, 'manifest.json'))

    def test_required_fields(self, manifest):
        """Check all required Web App Manifest fields are present."""
        required_fields = ['name', 'short_name', 'start_url', 'display', 'icons']
        for field in required_fields:
            assert field in manifest, f"Missing required field: {field}"

    def test_name_not_empty(self, manifest):
        assert len(manifest.get('name', '').strip()) > 0

    def test_short_name_not_empty(self, manifest):
        assert len(manifest.get('short_name', '').strip()) > 0

    def test_start_url(self, manifest):
        assert manifest['start_url'].startswith('/')

    def test_valid_display_mode(self, manifest):
        valid_modes = ['fullscreen', 'standalone', 'minimal-ui', 'browser']
        assert manifest['display'] in valid_modes

    def test_has_icons(self, manifest):
        icons = manifest.get('icons', [])
        assert len(icons) > 0, "manifest.json must include at least one icon"
        for icon in icons:
            assert 'src' in icon, "Each icon must have a 'src'"
            assert 'sizes' in icon, "Each icon must have 'sizes'"
            assert 'type' in icon, "Each icon must have 'type'"

    def test_theme_color(self, manifest):
        assert 'theme_color' in manifest
        assert manifest['theme_color'].startswith('#')

    def test_background_color(self, manifest):
        assert 'background_color' in manifest
        assert manifest['background_color'].startswith('#')


class TestServiceWorker:
    """Service worker structural tests."""

    @pytest.fixture
    def sw_content(self):
        sw_path = os.path.join(BASE_DIR, 'sw.js')
        with open(sw_path, 'r') as f:
            return f.read()

    def test_file_exists(self):
        assert os.path.exists(os.path.join(BASE_DIR, 'sw.js'))

    def test_install_event(self, sw_content):
        assert 'install' in sw_content

    def test_fetch_event(self, sw_content):
        assert 'fetch' in sw_content

    def test_activate_event(self, sw_content):
        assert 'activate' in sw_content

    def test_caches_api(self, sw_content):
        assert 'caches.open' in sw_content or 'caches.match' in sw_content

    def test_offline_page_caching(self, sw_content):
        assert 'offline' in sw_content.lower()

    def test_skip_waiting(self, sw_content):
        assert 'skipWaiting' in sw_content


class TestTemplateMetaTags:
    """Check required meta tags in all templates."""

    @pytest.fixture
    def templates_dir(self):
        return os.path.join(BASE_DIR, 'frontend', 'templates')

    @pytest.fixture
    def base_html(self, templates_dir):
        with open(os.path.join(templates_dir, 'base.html'), 'r') as f:
            return f.read()

    def test_base_has_viewport_meta(self, base_html):
        assert 'viewport' in base_html

    def test_viewport_has_device_width(self, base_html):
        assert 'width=device-width' in base_html

    def test_viewport_has_initial_scale(self, base_html):
        assert 'initial-scale=' in base_html

    def test_base_has_charset_meta(self, base_html):
        assert 'charset' in base_html

    def test_base_has_data_page_attribute(self, base_html):
        assert 'data-page' in base_html

    def test_mobile_css_linked_in_base(self, base_html):
        assert 'mobile-optimizations.css' in base_html

    def test_accessibility_css_linked_in_base(self, base_html):
        assert 'accessibility.css' in base_html

    def test_manifest_link_in_base(self, base_html):
        assert 'manifest' in base_html

    def test_service_worker_registration(self, base_html):
        assert 'serviceWorker' in base_html or 'sw.js' in base_html

    def test_offline_template_exists(self, templates_dir):
        assert os.path.exists(os.path.join(templates_dir, 'offline.html'))

    def test_offline_template_has_viewport(self, templates_dir):
        with open(os.path.join(templates_dir, 'offline.html'), 'r') as f:
            content = f.read()
        assert 'viewport' in content

    @pytest.mark.parametrize("template_name", [
        'index.html',
        'simulation.html',
        'agents.html',
        'gpu.html',
        'analytics.html',
        'settings.html',
    ])
    def test_all_templates_extend_base(self, templates_dir, template_name):
        path = os.path.join(templates_dir, template_name)
        if os.path.exists(path):
            with open(path, 'r') as f:
                content = f.read()
            assert 'extends "base.html"' in content


class TestMobileCSS:
    """Mobile optimization CSS tests."""

    @pytest.fixture
    def mobile_css(self):
        css_path = os.path.join(BASE_DIR, 'frontend', 'static', 'css', 'mobile-optimizations.css')
        with open(css_path, 'r') as f:
            return f.read()

    @pytest.fixture
    def css_files_list(self):
        css_dir = os.path.join(BASE_DIR, 'frontend', 'static', 'css')
        return [f for f in os.listdir(css_dir) if f.endswith('.css')]

    def test_file_exists(self):
        assert os.path.exists(os.path.join(BASE_DIR, 'frontend', 'static', 'css', 'mobile-optimizations.css'))

    def test_viewport_overflow_x_hidden(self, mobile_css):
        assert 'overflow-x' in mobile_css

    def test_touch_target_min_height(self, mobile_css):
        assert '48px' in mobile_css

    def test_form_input_font_size(self, mobile_css):
        assert '16px' in mobile_css

    def test_has_media_queries(self, mobile_css):
        assert '@media' in mobile_css

    def test_responsive_tables(self, mobile_css):
        assert 'overflow-x' in mobile_css or '-webkit-overflow-scrolling' in mobile_css

    def test_safe_area_support(self, mobile_css):
        assert 'safe-area-inset-bottom' in mobile_css

    def test_css_directory_not_empty(self, css_files_list):
        assert len(css_files_list) >= 4  # style.css, mobile-optimizations.css, accessibility.css, offline.css


class TestAccessibilityCSS:
    """Accessibility CSS tests."""

    @pytest.fixture
    def a11y_css(self):
        css_path = os.path.join(BASE_DIR, 'frontend', 'static', 'css', 'accessibility.css')
        with open(css_path, 'r') as f:
            return f.read()

    def test_file_exists(self):
        assert os.path.exists(os.path.join(BASE_DIR, 'frontend', 'static', 'css', 'accessibility.css'))

    def test_high_contrast_mode(self, a11y_css):
        assert 'high-contrast' in a11y_css or 'prefers-contrast' in a11y_css

    def test_reduced_motion(self, a11y_css):
        assert 'prefers-reduced-motion' in a11y_css or 'reduced-motion' in a11y_css

    def test_focus_indicators(self, a11y_css):
        assert 'focus-visible' in a11y_css or 'focus' in a11y_css
        assert 'outline' in a11y_css

    def test_screen_reader_support(self, a11y_css):
        assert 'sr-only' in a11y_css or 'aria-live' in a11y_css

    def test_large_text_mode(self, a11y_css):
        assert 'large-text' in a11y_css


class TestTouchGestures:
    """Touch gestures JavaScript tests."""

    @pytest.fixture
    def touch_js(self):
        js_path = os.path.join(BASE_DIR, 'frontend', 'static', 'js', 'touch-gestures.js')
        with open(js_path, 'r') as f:
            return f.read()

    def test_file_exists(self):
        assert os.path.exists(os.path.join(BASE_DIR, 'frontend', 'static', 'js', 'touch-gestures.js'))

    def test_swipe_detection(self, touch_js):
        assert 'touchstart' in touch_js
        assert 'touchend' in touch_js

    def test_long_press(self, touch_js):
        assert 'longPress' in touch_js or 'long-press' in touch_js or 'LONG_PRESS' in touch_js

    def test_double_tap(self, touch_js):
        assert 'double' in touch_js.lower() or 'Double' in touch_js or 'lastTapTime' in touch_js

    def test_pull_to_refresh_prevention(self, touch_js):
        assert 'touchmove' in touch_js

    def test_canvas_interaction(self, touch_js):
        assert 'canvas' in touch_js.lower() or 'world-canvas' in touch_js


class TestOfflinePage:
    """Offline page template and CSS tests."""

    def test_offline_html_exists(self):
        path = os.path.join(BASE_DIR, 'frontend', 'offline.html')
        if not os.path.exists(path):
            path = os.path.join(BASE_DIR, 'frontend', 'templates', 'offline.html')
        assert os.path.exists(path)

    def test_offline_css_exists(self):
        assert os.path.exists(os.path.join(BASE_DIR, 'frontend', 'static', 'css', 'offline.css'))

    def test_offline_html_has_retry_button(self):
        path = os.path.join(BASE_DIR, 'frontend', 'templates', 'offline.html')
        if not os.path.exists(path):
            pytest.skip("offline.html not found")
        with open(path, 'r') as f:
            content = f.read()
        assert 'offline' in content.lower()
        assert 'retry' in content.lower() or 'Try Again' in content

    def test_offline_html_has_indexeddb(self):
        path = os.path.join(BASE_DIR, 'frontend', 'templates', 'offline.html')
        if not os.path.exists(path):
            pytest.skip("offline.html not found")
        with open(path, 'r') as f:
            content = f.read()
        assert 'indexedDB' in content or 'indexeddb' in content.lower()

    def test_offline_css_matches_dark_theme(self):
        css_path = os.path.join(BASE_DIR, 'frontend', 'static', 'css', 'offline.css')
        with open(css_path, 'r') as f:
            content = f.read()
        assert '#1a1a2e' in content  # matches dark theme bg-primary
