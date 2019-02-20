import sublime
import sublime_plugin
from collections import namedtuple
import json

# Attempt to load urllib.request/error and fallback to urllib2 (Python 2/3 compat)
try:
    from urllib.request import urlopen
    from urllib.error import URLError
    from urllib.request import Request
except ImportError:
    from urllib2 import urlopen, URLError, Request

package_name = 'GitLab Snippets'

class GitLabSnippetCommand(sublime_plugin.WindowCommand):
    def run(self):
        active_view = self.window.active_view()

        if active_view and active_view.name() == package_name:
            self._close_gitlablist()
        else:
            self._open_gitlablist()

    def _close_gitlablist(self):
        gitlablist_view = self.window.active_view()
        view_settings = gitlablist_view.settings()
        previous_view_id = view_settings.get('previous_view_id')

        for v in self.window.views():
            if v.id() == previous_view_id:
                previous_view = v
                break

        self.window.focus_view(previous_view)
        gitlablist_view.close()

    def _open_gitlablist(self):
        new_view = self.window.new_file()
        new_view.settings().set(
            'previous_view_id', self.window.active_view().id())
        new_view.run_command('get_snippets')

class GetSnippetsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.set_scratch(True)
        self.view.set_name(package_name)
        self.view.set_syntax_file(
            'Packages/Markdown/Markdown.tmLanguage')

        self._construct_list(edit)
        self.view.window().focus_view(self.view)
        self._set_selection_on_first_line()

    def _construct_list(self, edit):
        settings = sublime.load_settings("Preferences.sublime-settings")
        url = settings.get("gitlab_url")
        token = settings.get("gitlab_token")
        snips = {}
        order_list = []
        line = 2

        list_data = namedtuple(
            'SnippetList',
            ['id', 'title', 'file_name'])

        snippets = '# GitLab Snippets\n\n'

        if url is None:
            self.view.insert(edit, 0, '[WARN] GitLab URL not defined, defaulting to gitlab.com.\n')
            url = 'https://gitlab.com'
        if token is None: 
            self.view.insert(edit, 0, '[ERROR] GitLab token not defined.\n')
            return None

        request = Request(url + '/api/v4/snippets', headers = {'PRIVATE-TOKEN': token})
        response = urlopen(request, timeout=5)
        list = response.read().decode('utf-8')
        for item in json.loads(list):
            snips[str(line)] = list_data(
                    id=item["id"], title=item["title"], file_name=item["file_name"])
            order_list.append((item["id"], line))
            snippets += '[' + item["visibility"] + '] ' + item["title"] + ' - ' + item["file_name"] + '\n'
            line += 1

        self.view.insert(edit, 0, snippets)
        self.view.settings().set('order_list', order_list)
        self.view.settings().set('snippets', snips)

    def _set_selection_on_first_line(self):
        point = self.view.text_point(2, 0)
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(point))
        self.view.show(point)


class GitLabSnippetsBindingListener(sublime_plugin.EventListener):

    def on_text_command(self, view, command_name, args):
        if view.name() == package_name:
            snippets_nav = TabListNavigaton(view)

            if command_name == 'move' and args['by'] == 'lines':
                return snippets_nav.move(forward=args['forward'])

            elif command_name == 'move' and args['by'] == 'characters':
                return ('show_file_contents', {})

            elif command_name == 'set_motion':
                if args.get('linewise'):
                    if args['motion_args'].get('by') == 'lines':
                        return snippets_nav.move(
                            forward=args['motion_args']['forward'])
                    else:
                        return ('extinguish_execution', {})
                else:
                    return snippets_nav.switch_to_tab()

            elif command_name == 'insert':
                return snippets_nav.switch_to_tab()

            elif command_name in ['switch_to_tab', 'exit_insert_mode',
                                  'show_file_contents']:
                return None

            else:
                return ('extinguish_execution', {})

    def on_deactivated(self, view):
        if view.name() == package_name:
            view.close()

class TabListNavigaton:
    def __init__(self, view):
        self.view = view

    def move(self, forward):
        snippets = self.view.settings().get('snippets')
        order_list = self.view.settings().get('order_list')

        line_num = self._get_line_number_under_sel()
        order = snippets[str(line_num)][1]

        last_item = False
        if forward:
            if (order + 1) > (len(order_list) - 1):
                point = self.view.text_point(0, 0)
            else:
                next_line_num = order_list[order+1][1]
                point = self.view.text_point(next_line_num-1, 0)

            if (order + 1) == (len(order_list) - 1):
                last_item = True
        else:
            if (order - 1) < 0:
                next_line_num = order_list[-1][1]
                point = self.view.text_point(next_line_num + 1, 0)
            else:
                next_line_num = order_list[order-1][1]
                point = self.view.text_point(next_line_num + 1, 0)

        self.view.sel().clear()
        self.view.sel().add(sublime.Region(point))
        self.view.show(point, show_surrounds=True)

        if last_item:
            layout_height = self.view.layout_extent()[1]
            viewport_height = self.view.viewport_extent()[1]
            if layout_height > viewport_height:
                new_pos = self.view.viewport_position()
                self.view.set_viewport_position((new_pos[0], new_pos[1] + 200))

    def switch_to_tab(self):
        line_num = self._get_line_number_under_sel()
        snippets = self.view.settings().get('snippets')

        return ('switch_to_tab', {'snippet_id': snippets[str(line_num)][0],'snippet_file_name': snippets[str(line_num)][2]})

    def _get_line_number_under_sel(self):
        selection_region = self.view.sel()[0]
        selected_row = self.view.rowcol(selection_region.a)[0]
        return selected_row

class SwitchToTabCommand(sublime_plugin.TextCommand):
    """Handler which opens selected tab """

    def run(self, edit, **kwargs):
        self.window = self.view.window()
        active_view = self.window.new_file()

        self._get_snippet_contents(edit, kwargs["snippet_id"], kwargs["snippet_file_name"], active_view)

    def _get_snippet_contents(self, edit, id, name, active_view):
        settings = sublime.load_settings("Preferences.sublime-settings")
        url = settings.get("gitlab_url")
        token = settings.get("gitlab_token")

        request = Request(url + '/api/v4/snippets/' + str(id) + '/raw', headers = {'PRIVATE-TOKEN': token})
        response = urlopen(request, timeout=5)

        contents = response.read().decode('utf_8').replace('\r', '')

        active_view.set_name(name)
        active_view.insert(edit, 0, contents)