#!/usr/bin/env python
# -*- coding: utf-8 -*-

import calendar
import datetime
import lxml.html
import re
import time
import twitter

from selenium import webdriver


# const
CONSUMER_KEY = '*************************'
CONSUMER_SECRET = '**************************************************'
ACCESS_TOKEN = '******************-*******************************'
ACCESS_TOKEN_SECRET = '*********************************************'

WORK_DAY = 4 # 月曜を0、日曜を6として稼動する曜日を整数で定義

def scrape_program_table(driver):
    u'''ABNの番組表をスクレイピングして放送日と時間を取得
    @param  driver PhantomJSのドライバー
    @return 放送日と時間(key = ('date', 'time'))
    '''

    url = 'http://www.abn-tv.co.jp/programtable/'
    driver.get(url)
    root = lxml.html.fromstring(driver.page_source)

    days = []
    pattern = re.compile('^(\d{1,2})/(\d{1,2})\((.{1})\)$') # 例: '01/01(日)'
    todya = datetime.datetime.now()
    for td in root.cssselect('table.tbl-programweek > thead > tr > td'):
        date = None
        match = pattern.search(td.text_content())
        if match:
            month, day, weekday = match.groups()
            year = todya.year
            month = int(month)
            day = int(day)
            if month < todya.month:
                year = todya.year + 1 # 今日が12月で1月が回ってきた場合は年を来年に
            date = datetime.datetime(year, month, day)
        days.append(date)

    for tr in root.cssselect('table.tbl-programweek > tbody > tr'):
        idx = 0
        for td in tr.cssselect('td'):
            for div in td.cssselect('div.program-info'):
                name = div.cssselect('p.name')
                if not name:
                    continue
                else:
                    name = lxml.html.tostring(name[0], method='text', encoding='unicode')
                pattern = re.compile(u'タモリ倶楽部')
                match = pattern.search(name)
                if not match:
                    continue

                time = div.cssselect('time')
                if not time:
                    break
                time = time[0].text_content()
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

def scrape_backnumber(driver, date):
    u'''番組公式（のモバイル）サイトをスクレイピングして
    15日前（前々回）の放送内容のバックナンバーを取得
    @param  driver PhantomJSのドライバー
    @param  date 放送日
    @return 放送内容
    '''

    delay = -15
    url = 'http://www.tv-asahi.co.jp/tamoriclub/sphone/backnumber.html'
    driver.get(url)
    root = lxml.html.fromstring(driver.page_source)

    date = date + datetime.timedelta(days=delay)
    pattern = re.compile(u'^(\d{1,2})月(\d{1,2})日$')
    for section in root.cssselect('section.card'):
        for h2 in section.cssselect('h2'):
            match = pattern.search(h2.text_content())
            if match:
                month, day = match.groups()
                if int(month) is date.month and int(day) is date.day:
                    for p in section.cssselect('p'):
                        return p.text_content().encode('utf-8')
                else:
                    continue

if __name__ == '__main__':
    api = twitter.Api(consumer_key=CONSUMER_KEY, consumer_secret=CONSUMER_SECRET, access_token_key=ACCESS_TOKEN, access_token_secret=ACCESS_TOKEN_SECRET)
    today = datetime.datetime.now()
    if today.weekday() is WORK_DAY:
        # 今日が稼働日であれば無条件に実行
        pass
    else:
        # 稼働日の曜日以外だった場合は直近のツイートの日付を確認
        for tw in api.GetUserTimeline():
            time_utc = time.strptime(tw.created_at, '%a %b %d %H:%M:%S +0000 %Y')
            unix_time = calendar.timegm(time_utc)
            time_local = time.localtime(unix_time)

            last_tw = datetime.datetime.fromtimestamp(time.mktime(time_local))
            elapsed = last_tw - today
            if elapsed.days <= 7:
                # 直近のツイートが1週間以内の場合は何もせず終了
                exit()
            else:
                # 直近のツイートから1週間以上経過している場合は
                # 何らかの理由で前回の処理が実行されていないので再試行
                break

    # PhantomJSで擬似的にブラウザでWEBアクセスする（JavaScriptが実行される必要があるため）
    driver = webdriver.PhantomJS()

    oa_datetime = None
    try:
        # ABNの番組表をスクレイピングして放送日と時間を取得
        oa_datetime = scrape_program_table(driver)
    except Exception as ex:
        print ex.message

    plot = None
    if oa_datetime:
        try:
            # 番組公式（のモバイル）サイトをスクレイピングして
            # 15日前（前々回）の放送内容のバックナンバーを取得
            plot = scrape_backnumber(driver, oa_datetime['date'])
        except Exception as ex:
            print ex.message

    # PhantomJSのドライバーを終了
    driver.quit()

    if plot:
        # 放送内容が取得されていればツイートを実行
        print api.PostUpdate('%s年%s月%s日 %s～ %s' % (oa_datetime['date'].year, oa_datetime['date'].month, oa_datetime['date'].day, oa_datetime['time'], plot))

