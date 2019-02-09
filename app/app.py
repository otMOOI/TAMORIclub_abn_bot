#!/usr/bin/env python
# -*- coding: utf-8 -*-

import calendar
import datetime
import re
import time
import twitter
import urllib

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options

# 定数
__CONSUMER_KEY = '*************************'
__CONSUMER_SECRET = '**************************************************'
__ACCESS_TOKEN = '******************-*******************************'
__ACCESS_TOKEN_SECRET = '*********************************************'

__SCREEN_NAME = '**************'

__WORK_HOUR = 19 # 稼動する時刻（UTCでの指定なので日本時間の4:00a.m.）
__WORK_DAY = 3 # 稼動する曜日（Pythonでは月曜を0、日曜を6として定義しているので木曜日）

def scrape_program_table(driver):
    u'''ABNの番組表をスクレイピングして放送日と時間を取得
    @param  driver HeadlessChromeのドライバー
    @return 放送日と時間(key = ('date', 'time'))
    '''

    url = 'http://www.abn-tv.co.jp/programtable/'
    driver.get(url)

    days = []
    pattern = re.compile('^(\d{1,2})/(\d{1,2})\((.{1})\)$') # 例: '01/01(日)'
    todya = datetime.datetime.now()
    for td in driver.find_elements_by_css_selector('table.tbl-programweek > thead > tr > td'):
        date = None
        match = pattern.search(td.text)
        if match:
            month, day, weekday = match.groups()
            year = todya.year
            month = int(month)
            day = int(day)
            if month < todya.month:
                year = todya.year + 1 # 今日が12月で1月が回ってきた場合は年を来年に
            date = datetime.datetime(year, month, day)
        days.append(date)

    for tr in driver.find_elements_by_css_selector('table.tbl-programweek > tbody > tr'):
        idx = 0
        for td in tr.find_elements_by_css_selector('td'):
            for div in td.find_elements_by_css_selector('div.program-info'):
                name = div.find_elements_by_css_selector('p.name')
                if not name:
                    continue
                else:
                    name = name[0].text
                pattern = re.compile(u'タモリ倶楽部')
                match = pattern.search(name)
                if not match:
                    continue

                time = div.find_elements_by_css_selector('time')
                if not time:
                    break
                time = time[0].text
                pattern = re.compile('^(\d{1,2}):(\d{1,2})$')
                match = pattern.search(time)
                if not match:
                    break
                hour, minute = match.groups()
                return {
                    'date': datetime.datetime(days[idx].year, days[idx].month, days[idx].day),
                    'time': '%02d:%02d' % (int(hour), int(minute))
                }
            idx = idx + 1

def scrape_backnumber(driver, date, delay):
    u'''番組公式サイトをスクレイピングしてバックナンバーから指定日数前の放送内容を取得
    @param  driver HeadlessChromeのドライバー
    @param  date 放送日
    @param  delay 遅れ日数
    @return 放送内容
    '''

    url = urllib.quote('https://www.tv-asahi.co.jp/tamoriclub/#/バックナンバー?category=variety', safe=':/#?=&')
    driver.get(url)

    plot = None
    url = None

    date = date + datetime.timedelta(days=delay)
    pattern = re.compile(u'(\d{1,2})月\s*(\d{1,2})日')
    for a in driver.find_elements_by_css_selector('div#ipg-backnumber > a'):
        match = pattern.search(a.text)
        if match:
            month, day = match.groups()
            if int(month) is date.month and int(day) is date.day:
                url = urllib.quote(a.get_attribute('href').encode('utf-8'), safe=':/#?=&')
                break
            else:
                continue

    if url:
        driver.get(url)
        for div in driver.find_elements_by_css_selector("div.ipg-backnumber-article-text"):
            plot = div.text
            break

    return plot

if __name__ == '__main__':
    api = twitter.Api(consumer_key=__CONSUMER_KEY,
                    consumer_secret=__CONSUMER_SECRET,
                    access_token_key=__ACCESS_TOKEN,
                    access_token_secret=__ACCESS_TOKEN_SECRET)
    today = datetime.datetime.now()

    if today.hour is not __WORK_HOUR:
        # 19時～20時（日本時間4時～5時）以外の時間帯以外なら何もせず終了
        exit()

    if today.weekday() is __WORK_DAY:
        # 今日が稼働日であれば無条件に実行
        pass
    else:
        # 稼働日の曜日以外だった場合は直近のツイートの日付を確認
        for tw in api.GetUserTimeline():
            time_utc = time.strptime(tw.created_at, '%a %b %d %H:%M:%S +0000 %Y')
            unix_time = calendar.timegm(time_utc)
            time_local = time.localtime(unix_time)

            last_tw = datetime.datetime.fromtimestamp(time.mktime(time_local))
            elapsed = today - last_tw
            if elapsed.days <= 7:
                # 直近のツイートが1週間以内の場合は何もせず終了
                exit()
            else:
                # 直近のツイートから1週間以上経過している場合は
                # 何らかの理由で前回の処理が実行されていないので再試行
                break

    # HeadlessChromeで擬似的にブラウザでWEBアクセスする（JavaScriptが実行される必要があるため）
    options = Options()
    options.add_argument('--headless')
    '''
    driver = webdriver.Chrome(chrome_options=options)
    '''
    options.binary_location = '/app/.apt/usr/bin/google-chrome'
    driver = webdriver.Chrome(executable_path='chromedriver', chrome_options=options)

    oa_datetime = None
    try:
        # ABNの番組表をスクレイピングして放送日と時間を取得
        oa_datetime = scrape_program_table(driver)
    except Exception as ex:
        print ex.message

    plot = None
    if oa_datetime:
        try:
            delay = -8 # 遅れ日数
            # twitterアカウントのプロフィール文章から遅れ日数を取得
            user_info = api.GetUser(screen_name=__SCREEN_NAME)
            match = re.search(r'（(\d+)日遅れ）', user_info.description.encode('utf-8'))

            if match:
                delay = -1 * int(match.group(1))
            # 番組公式サイトをスクレイピングして
            # 放送内容のバックナンバーを取得
            plot = scrape_backnumber(driver, oa_datetime['date'], delay)
        except Exception as ex:
            print ex.message

    # HeadlessChromeのドライバーを終了
    driver.quit()

    if plot:
        # 放送内容が取得されていればツイートを実行
        if len(plot) > 120:
            # 放送内容が120文字を超える場合は先頭から80文字と末尾40文字に省略
            plot = plot[:80] + u'……' + plot[-40:]
        print api.PostUpdate(u'%s年%s月%s日 %s～ %s' % (oa_datetime['date'].year, oa_datetime['date'].month, oa_datetime['date'].day, oa_datetime['time'], plot))
