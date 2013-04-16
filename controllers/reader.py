# Copyright 2012 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Controllers for the Oppia reader view."""

__author__ = 'Sean Lip'

import cgi
import json

from controllers.base import BaseHandler
import feconf
from models.exploration import Exploration
from models.state import Content
from models.state import State
from models.statistics import EventHandler
from models.widget import InteractiveWidget
from models.widget import NonInteractiveWidget
import utils

READER_MODE = 'reader'
DEFAULT_ANSWERS = {'NumericInput': 0, 'SetInput': {}, 'TextInput': ''}


def parse_content_into_html(content_array, block_number, params=None):
    """Takes a Content array and transforms it into HTML.

    Args:
        content_array: an array, each of whose members is of type Content. This
            object has two keys: type and value. The 'type' is one of the
            following:
                - 'text'; then the value is a text string
                - 'image'; then the value is an image ID
                - 'video'; then the value is a video ID
                - 'widget'; then the value is a widget ID
        block_number: the number of content blocks preceding this one.
        params: any parameters used for templatizing text strings.

    Returns:
        the HTML string representing the array.

    Raises:
        InvalidInputException: if content has no 'type' attribute, or an invalid
            'type' attribute.
    """
    if params is None:
        params = {}

    html = ''
    widget_array = []
    widget_counter = 0
    for content in content_array:
        if content.type == 'widget':
            try:
                widget = NonInteractiveWidget.get_with_params(
                    content.value, params)
                widget_counter += 1
                html += feconf.JINJA_ENV.get_template('content.html').render({
                    'type': content.type, 'blockIndex': block_number,
                    'index': widget_counter})
                widget_array.append({
                    'blockIndex': block_number,
                    'index': widget_counter,
                    'code': widget.raw})
            except utils.EntityIdNotFoundError:
                # Ignore empty widget content.
                pass
        elif (content.type in ['text', 'image', 'video']):
            if content.type == 'text':
                value = utils.parse_with_jinja(content.value, params)
            else:
                value = content.value

            html += feconf.JINJA_ENV.get_template('content.html').render({
                'type': content.type, 'value': value})
        else:
            raise utils.InvalidInputException(
                'Invalid content type %s', content.type)
    return html, widget_array


class ExplorationPage(BaseHandler):
    """Page describing a single exploration."""

    def get(self, exploration_id):
        """Handles GET requests."""
        self.values.update({
            'js': utils.get_js_controllers(['readerExploration']),
            'nav_mode': READER_MODE,
        })

        Exploration.get(exploration_id)

        # The following allows embedding of Oppia explorations in other pages.
        if self.request.get('iframed') == 'true':
            self.values['iframed'] = True

        self.render_template('reader/reader_exploration.html')


class ExplorationHandler(BaseHandler):
    """Provides the data for a single exploration."""

    def get_params(self, state, existing_params=None):
        """Updates existing parameters based on changes in the given state."""
        if existing_params is None:
            existing_params = {}
        # Modify params using param_changes.
        # TODO(sll): Define this behavior. Currently a new parameter is set
        # only if it doesn't exist, but it might be the case that the parameter
        # should be reset each time the state is entered.
        for item in state.param_changes:
            if item.name not in existing_params:
                # Pick a random parameter for this key.
                existing_params[item.name] = utils.get_random_choice(item.values)
        return existing_params

    def append_feedback(self, feedback, html_output, widget_output,
                        block_number, params):
        """Appends Oppia's feedback to the output variables."""
        feedback_bits = [cgi.escape(bit) for bit in feedback.split('\n')]
        action_html, action_widgets = parse_content_into_html(
            [Content(type='text', value='<br>'.join(feedback_bits))],
            block_number,
            params)
        html_output += action_html
        widget_output.append(action_widgets)
        return html_output, widget_output

    def get(self, exploration_id):
        """Populates the data on the individual exploration page."""
        # TODO(sll): Maybe this should send a complete state machine to the
        # frontend, and all interaction would happen client-side?
        exploration = Exploration.get(exploration_id)
        init_state = exploration.init_state.get()
        params = self.get_params(init_state)
        init_html, init_widgets = parse_content_into_html(
            init_state.content, 0, params)
        interactive_widget_html = InteractiveWidget.get_raw_code(
            init_state.widget.widget_id,
            params=utils.parse_dict_with_params(
                init_state.widget.params, params)
        )

        self.values.update({
            'block_number': 0,
            'interactive_widget_html': interactive_widget_html,
            'interactive_params': init_state.widget.params,
            'oppia_html': init_html,
            'params': params,
            'state_id': init_state.id,
            'title': exploration.title,
            'widgets': init_widgets,
        })
        if init_state.widget.widget_id in DEFAULT_ANSWERS:
            self.values['default_answer'] = (
                DEFAULT_ANSWERS[init_state.widget.widget_id])
        self.response.write(json.dumps(self.values))

        EventHandler.record_exploration_visited(exploration_id)
        EventHandler.record_state_hit(exploration_id, init_state.id)

    def post(self, exploration_id, state_id):
        """Handles feedback interactions with readers."""
        values = {'error': []}

        exploration = Exploration.get(exploration_id)
        state = State.get(state_id, exploration)
        old_state = state

        payload = json.loads(self.request.get('payload'))

        # The 0-based index of the last content block already on the page.
        block_number = payload.get('block_number')
        params = self.get_params(state, payload.get('params'))
        # The reader's answer.
        answer = payload.get('answer')
        # The answer handler (submit, click, etc.)
        handler = payload.get('handler')

        # Add the reader's answer to the parameter list. This must happen before
        # the interactive widget is constructed.
        params['answer'] = answer

        dest_id, feedback, rule, recorded_answer = state.transition(
            answer, params, handler)

        if recorded_answer:
            recorded_answer = json.dumps(recorded_answer)
            EventHandler.record_rule_hit(
                exploration_id, state_id, rule, recorded_answer)
            # Add this answer to the state's 'unresolved answers' list.
            if recorded_answer not in old_state.unresolved_answers:
                old_state.unresolved_answers[recorded_answer] = 0
            old_state.unresolved_answers[recorded_answer] += 1
            # TODO(sll): Make this async?
            old_state.put()

        assert dest_id

        html_output, widget_output = '', []
        # TODO(sll): The following is a special-case for multiple choice input,
        # in which the choice text must be displayed instead of the choice
        # number. We might need to find a way to do this more generically.
        if state.widget.widget_id == 'MultipleChoiceInput':
            answer = state.widget.params['choices'][int(answer)]

        # Append reader's answer.
        values['reader_html'] = feconf.JINJA_ENV.get_template(
            'reader_response.html').render({'response': answer})

        if dest_id == feconf.END_DEST:
            # This leads to a FINISHED state.
            if feedback:
                html_output, widget_output = self.append_feedback(
                    feedback, html_output, widget_output, block_number, params)
            EventHandler.record_exploration_completed(exploration_id)
        else:
            state = State.get(dest_id, exploration)
            EventHandler.record_state_hit(exploration_id, state_id)

            if feedback:
                html_output, widget_output = self.append_feedback(
                    feedback, html_output, widget_output, block_number, params)

            # Append text for the new state only if the new and old states
            # differ.
            if old_state.id != state.id:
                state_html, state_widgets = parse_content_into_html(
                    state.content, block_number, params)
                # Separate text for the new state and feedback for the old state
                # by an additional line.
                if state_html and feedback:
                    html_output += '<br>'
                html_output += state_html
                widget_output.append(state_widgets)

        if state.widget.widget_id in DEFAULT_ANSWERS:
            values['default_answer'] = DEFAULT_ANSWERS[state.widget.widget_id]
        values.update({
            'exploration_id': exploration.id, 'state_id': state.id,
            'oppia_html': html_output, 'widgets': widget_output,
            'block_number': block_number + 1, 'params': params
        })

        if dest_id != feconf.END_DEST:
            values['finished'] = False
            if state.widget.sticky and (
                    state.widget.widget_id == old_state.widget.widget_id):
                values['interactive_widget_html'] = ''
                values['sticky_interactive_widget'] = True
            else:
                values['interactive_widget_html'] = (
                    InteractiveWidget.get_raw_code(
                        state.widget.widget_id,
                        params=utils.parse_dict_with_params(
                            state.widget.params, params)
                    )
                )
        else:
            values['finished'] = True
            values['interactive_widget_html'] = ''

        self.response.write(json.dumps(values))


class RandomExplorationPage(BaseHandler):
    """Returns the page for a random exploration."""

    def get(self):
        """Handles GET requests."""
        explorations = Exploration.query().filter(
            Exploration.is_public == True).fetch(100)

        # Don't use the first exploration; users will have seen that already
        # on the main page.
        selected_exploration = utils.get_random_choice(explorations[1:])

        self.redirect('/learn/%s' % selected_exploration.id)
