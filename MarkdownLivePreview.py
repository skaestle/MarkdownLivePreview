"""
Terminology
markdown_view: the view of the markdown file
preview_view: the preview tab, opened beside markdown_view like a ctrl+clicked tab
"""

import time
import os.path
import struct
import sublime
import sublime_plugin

from functools import partial

from .markdown2html import markdown2html

MARKDOWN_VIEW_INFOS = "markdown_view_infos"
PREVIEW_VIEW_INFOS = "preview_view_infos"
SETTING_DELAY_BETWEEN_UPDATES = "delay_between_updates"

resources = {}

# markdown_view.id(): phantom set
phantom_sets = {}
last_update = 0


def plugin_loaded():
    global DELAY
    resources["base64_404_image"] = parse_image_resource(get_resource("404.base64"))
    resources["base64_loading_image"] = parse_image_resource(
        get_resource("loading.base64")
    )
    resources["stylesheet"] = get_resource("stylesheet.css")
    # FIXME: how could we make this setting update without restarting sublime text
    #        and not loading it every update as well
    DELAY = get_settings().get(SETTING_DELAY_BETWEEN_UPDATES)


def find_preview_view(markdown_view):
    infos = markdown_view.settings().get(MARKDOWN_VIEW_INFOS)
    if not infos:
        return None
    preview_view = sublime.View(infos["preview_view_id"])
    return preview_view if preview_view.is_valid() else None


class OpenMarkdownPreviewCommand(sublime_plugin.TextCommand):
    """ Toggles the preview tab beside the markdown view """

    def run(self, edit):
        markdown_view = self.view
        preview_view = find_preview_view(markdown_view)
        if preview_view:
            preview_view.close()
            return

        window = markdown_view.window()
        preview_view = window.new_file(flags=sublime.ADD_TO_SELECTION)
        preview_view.set_scratch(True)
        preview_view.set_name(
            "Preview: " + os.path.basename(markdown_view.file_name() or "untitled")
        )
        settings = preview_view.settings()
        settings.set(PREVIEW_VIEW_INFOS, {"markdown_view_id": markdown_view.id()})
        settings.set("gutter", False)
        settings.set("line_numbers", False)
        settings.set("draw_indent_guides", False)
        preview_view.set_read_only(True)

        markdown_view.settings().set(
            MARKDOWN_VIEW_INFOS, {"preview_view_id": preview_view.id()}
        )
        phantom_sets[markdown_view.id()] = sublime.PhantomSet(preview_view)
        window.focus_view(markdown_view)
        update_preview(markdown_view)

    def is_enabled(self):
        # FIXME: is this the best way there is to check if the current syntax is markdown?
        #        should we only support default markdown?
        #        what about "md"?
        # FIXME: what about other languages, where markdown preview roughly works?
        return "markdown" in self.view.settings().get("syntax").lower()


class MarkdownLivePreviewListener(sublime_plugin.EventListener):
    def on_pre_close(self, view):
        if view.settings().get(MARKDOWN_VIEW_INFOS):
            preview_view = find_preview_view(view)
            phantom_sets.pop(view.id(), None)
            view.settings().erase(MARKDOWN_VIEW_INFOS)
            if preview_view:
                preview_view.close()

        infos = view.settings().get(PREVIEW_VIEW_INFOS)
        if infos:
            markdown_view = sublime.View(infos["markdown_view_id"])
            phantom_sets.pop(markdown_view.id(), None)
            if markdown_view.is_valid():
                markdown_view.settings().erase(MARKDOWN_VIEW_INFOS)

    def on_modified_async(self, markdown_view):
        if markdown_view.id() not in phantom_sets:
            return
        sublime.set_timeout(partial(update_preview, markdown_view), DELAY)


def update_preview(markdown_view):
    global last_update

    # also a callback for images loaded from the internet, possibly after closing
    if time.time() - last_update < DELAY / 1000:
        return

    preview_view = find_preview_view(markdown_view)
    phantom_set = phantom_sets.get(markdown_view.id())
    if not markdown_view.is_valid() or not preview_view or not phantom_set:
        return

    last_update = time.time()

    total_region = sublime.Region(0, markdown_view.size())
    markdown = markdown_view.substr(total_region)

    viewport_width = preview_view.viewport_extent()[0]

    basepath = os.path.dirname(markdown_view.file_name() or "")
    html = markdown2html(
        markdown,
        basepath,
        partial(update_preview, markdown_view),
        resources,
        viewport_width,
    )

    phantom_set.update(
        [
            sublime.Phantom(
                sublime.Region(0),
                html,
                sublime.LAYOUT_BLOCK,
                lambda href: sublime.run_command("open_url", {"url": href}),
            )
        ]
    )


def get_settings():
    return sublime.load_settings("MarkdownLivePreview.sublime-settings")


def get_resource(resource):
    path = "Packages/MarkdownLivePreview/resources/" + resource
    abs_path = os.path.join(sublime.packages_path(), "..", path)
    if os.path.isfile(abs_path):
        with open(abs_path, "r") as fp:
            return fp.read()
    return sublime.load_resource(path)


def parse_image_resource(text):
    width, height, base64_image = text.splitlines()
    return base64_image, (int(width), int(height))


# try to reload the resources if we save this file
try:
    plugin_loaded()
except OSError:
    pass
