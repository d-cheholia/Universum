# pylint: disable = redefined-outer-name

import os
import pytest

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.webelement import FirefoxWebElement


config = """
from universum.configuration_support import Configuration

success_step = Configuration([dict(name="Success step", command=["echo", "success"])])
failed_step = Configuration([dict(name="Failed step", command=["./non_existing_script.sh"])])
partially_success_step = Configuration([dict(name="Partially success step: ")])
all_success_step = Configuration([dict(name="All success step: ")])
all_failed_step = Configuration([dict(name="All failed step: ")])

configs = \
    success_step + \
    failed_step + \
    partially_success_step * (success_step + failed_step) + \
    all_success_step * (success_step + success_step) + \
    all_failed_step * (failed_step + failed_step)
"""


@pytest.fixture()
def browser():
    options = Options()
    options.headless = True
    firefox = webdriver.Firefox(options=options)
    yield firefox
    firefox.close()


def test_success(docker_main_and_nonci, browser):
    docker_main_and_nonci.run(config, additional_parameters="--html-log")
    check_html_log(docker_main_and_nonci.artifact_dir, browser)


def test_success_clean_build(docker_main, browser):
    docker_main.run(config, additional_parameters="--html-log --clean-build")
    check_html_log(docker_main.artifact_dir, browser)


def test_no_html_log_requested(docker_main_and_nonci):
    docker_main_and_nonci.run(config)
    log_path = os.path.join(docker_main_and_nonci.artifact_dir, "log.html")
    assert not os.path.exists(log_path)


def check_html_log(artifact_dir, browser):
    log_path = os.path.join(artifact_dir, "log.html")
    assert os.path.exists(log_path)

    browser.get(f"file://{log_path}")
    html_body = browser.find_element_by_tag_name("body")
    body_elements = html_body.find_elements_by_xpath("./*")
    assert len(body_elements) == 1
    assert body_elements[0].tag_name == "pre"

    pre_element = TestElement.create(body_elements[0])
    steps_section = pre_element.get_section_by_name("Executing build steps")
    steps_body = steps_section.get_section_body()

    check_step_collapsed(steps_section, steps_body)
    steps_section.click()
    check_step_not_collapsed(steps_section, steps_body)
    check_sections_indentation(steps_section)
    steps_section.click()
    check_step_collapsed(steps_section, steps_body)


def check_sections_indentation(steps_section):
    steps_body = steps_section.get_section_body()
    step_lvl1_first = steps_body.get_section_by_name("Failed step")
    step_lvl1_second = steps_body.get_section_by_name("Partially success step")
    assert step_lvl1_first.indent == step_lvl1_second.indent

    step_lvl1_second.click()
    step_lvl1_body = step_lvl1_second.get_section_body()
    step_lvl2_first = step_lvl1_body.get_section_by_name("Success step")
    step_lvl2_second = step_lvl1_body.get_section_by_name("Failed step")
    assert step_lvl2_first.indent == step_lvl2_second.indent

    assert steps_section.indent < step_lvl1_first.indent < step_lvl2_first.indent


def check_step_collapsed(section, body):
    assert section.is_section_collapsed
    assert body.is_body_collapsed
    assert not body.is_displayed()


def check_step_not_collapsed(section, body):
    assert not section.is_section_collapsed
    assert not body.is_body_collapsed
    assert body.is_displayed()


class TestElement(FirefoxWebElement):

    @staticmethod
    def create(element):
        assert element
        element.__class__ = TestElement
        return element

    # <input type="checkbox" id="1." class="hide">
    # <label for="1.">  <-- returning this element
    #     <span class="sectionLbl">1. Section name</span>  <-- Searching for this element
    # </label>
    # <div>Section body</div>
    def get_section_by_name(self, section_name):
        span_elements = self.find_elements_by_class_name("sectionLbl")
        result = None
        for el in span_elements:
            if section_name in el.text:
                result = el.find_element_by_xpath("..")
        return TestElement.create(result)

    def get_section_body(self):
        body = TestElement.create(self.find_element_by_xpath("./following-sibling::*[1]"))
        assert body.tag_name == "div"
        return body

    @property
    def is_body_collapsed(self):
        display_state = self.value_of_css_property("display")
        collapsed_state = "none"
        not_collapsed_state = "block"
        if display_state not in (collapsed_state, not_collapsed_state):
            raise RuntimeError(f"Unexpected element display state: '{display_state}'")

        collapsed = (display_state == collapsed_state)
        collapsed &= (not self.text)
        return collapsed

    @property
    def is_section_collapsed(self):
        label_span = self.find_element_by_tag_name("span")
        assert label_span
        script = "return window.getComputedStyle(arguments[0],':before').getPropertyValue('content')"
        section_state = self.parent.execute_script(script, label_span).replace('"', "").replace(" ", "")
        collapsed_state = "[+]"
        not_collapsed_state = "[-]"
        if section_state not in (collapsed_state, not_collapsed_state):
            raise RuntimeError(f"Unexpected section collapsed state: '{section_state}'")

        return section_state == collapsed_state

    @property
    def indent(self):
        return self.location['x']