import argparse
import sys
from subprocess import call

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver import DesiredCapabilities
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import visibility_of_element_located
from selenium.webdriver.support.wait import WebDriverWait

from plexapi import CONFIG
from plexapi.compat import which, parse_qsl
from plexapi.myplex import MyPlexAccount

DOCKER_CMD = [
    'docker', 'run', '-d',
    '--net', '%(network)s',
    '--name', 'plex-test-client',
    '--restart', 'on-failure',
    '-p', '4444:4444/tcp',
    '--shm-size', '2g',
    '-e', 'GRID_CLEAN_UP_CYCLE=600000',
    'selenium/standalone-chrome'
]


class element_has_css_class(object):
    """ An expectation for checking that an element has a particular css class.

    locator - used to find the element
    returns the WebElement once it has the particular css class
    """

    def __init__(self, locator, css_class):
        self.locator = locator
        self.css_class = css_class

    def __call__(self, driver):
        element = driver.find_element(*self.locator)  # Finding the referenced element
        if self.css_class in element.get_attribute("class").split(' '):
            return element
        else:
            return False


def is_library_or_users(driver):
    try:
        element = driver.find_element(By.XPATH, '//li[@class="user-select-list-item"]')
    except NoSuchElementException:
        element = driver.find_element(By.XPATH, '//div[@role="header"][text()="Online Content"]')

    return element


if __name__ == '__main__':
    if which('docker') is None:
        print('Docker is required to be available')
        exit(1)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', help='Your Plex username', default=CONFIG.get('auth.myplex_username'),
                        required=True)
    parser.add_argument('--password', help='Your Plex password', default=CONFIG.get('auth.myplex_password'),
                        required=True)
    parser.add_argument('--docker-network', help='Docker network name, where plex server is located',
                        default='plex-test')
    parser.add_argument('--pin', help='If the user has a pin you should provide it')
    opts = parser.parse_args()
    if call(['docker', 'pull', 'selenium/standalone-chrome'], stdout=sys.stderr) != 0:
        print('Got an error when executing docker pull!')
        exit(1)

    arg_bindings = {
        'network': opts.docker_network,
    }

    docker_cmd = [c % arg_bindings for c in DOCKER_CMD]

    exit_code = call(docker_cmd, stdout=sys.stderr)
    if exit_code != 0:
        exit(exit_code)

    wd = webdriver.Remote(command_executor='http://127.0.0.1:4444/wd/hub',
                          desired_capabilities=DesiredCapabilities.CHROME)

    wd.get('https://app.plex.tv')
    btn = WebDriverWait(wd, 10).until(
        visibility_of_element_located((By.XPATH, '//button[@data-qa-id="signIn--email"]'))
    )
    WebDriverWait(wd, 10).until_not(
        element_has_css_class((By.XPATH, '//button[@data-qa-id="signIn--email"]'), 'isDisabled')
    )
    btn.click()
    current_url = wd.current_url
    params = dict(parse_qsl(current_url.split('#!?')[1]))
    client_id = params['clientID']

    submit = WebDriverWait(wd, 3).until(
        visibility_of_element_located((By.XPATH, '//button[@type="submit"]'))
    )
    wd.find_element_by_id('email').send_keys('andrey@janzen.su')
    wd.find_element_by_id('password').send_keys('7.fpKbLXJF.7dxoX2iPC')
    submit.click()

    elm = WebDriverWait(wd, 10).until(is_library_or_users)

    if elm.get_attribute('class') == 'user-select-list-item':
        xpath = '//li[@class="user-select-list-item"]/a[div[@class="username"][text()="%s"]]' % 'andrey@janzen.su'

        try:
            wd.find_element_by_xpath(xpath + '[div/i[@class="protected-icon user-icon glyphicon lock"]]').click()
            # if we're haven't got an exception yet then the use has pin-protection
            if not opts.pin:
                raise Exception('You have to provide a PIN')
            for c in {opts.pin}:
                wd.switch_to.active_element.send_keys(c)
        except NoSuchElementException:
            wd.find_element_by_xpath(xpath).click()

        WebDriverWait(wd, 10).until(
            visibility_of_element_located((By.XPATH, '//div[@role="header"][text()="Online Content"]'))
        )

    account = MyPlexAccount(opts.username, opts.password)
    client = None
    for device in account.devices():
        if device.clientIdentifier == client_id:
            client = device
            break

    if not client:
        raise Exception('Unable to find the client in you MyPlex account')

    print('PLEXAPI_AUTH_CLIENT_TOKEN=' + client.token)
