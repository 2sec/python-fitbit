# coding=utf-8

import os
import sys

import time
from datetime import datetime 
from datetime import timedelta
import requests

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.dates import num2date
from matplotlib.dates import date2num


from matplotlib import rcParams
rcParams['font.family'] = 'sans-serif'
rcParams['font.sans-serif'] = 'Hermit'

debug = False
token = None



# call the Fitbit API
# returns the response as json
def call_fitbit_api(url):
    if debug: 
        empty_response = { 'activities-calories-intraday':  { 'dataset': [] }, 'activities-heart-intraday':  { 'dataset': [] }, 'sleep': [] }
        return empty_response

    
    headers = {'Authorization': 'Bearer %s' % token}

    while True:
        try:
            r = requests.get(url, headers = headers)

            if r.status_code == 200:
                data = r.json()
                return data

            # TODO: test below code
            print('Error\nHeaders=%s\nContent=%s' % (r.headers, r.content))

            if r.status != 429:
                return None

            reset = r.Headers['Fitbit-Rate-Limit-Reset']
            print('Rate limit reached: retry after %.02f hours' % reset/3600.0)
            print('pausing...')
            time.sleep(reset + 60)

        except Exception as e:
            print('Exception\n%s' % e)
            print('pausing...')
            time.sleep(5)
            


# get the last modify date of a file
def get_modify_date(filename):
    if not os.path.isfile(filename):
        return None
        
    modify_date = datetime.fromtimestamp(os.path.getmtime(filename))
    return modify_date


# test if the given file is complete based on its last modify date or if has to be regenerated
def must_regenerate(filename, date):
    regenerate = True

    modify_date = get_modify_date(filename)
    if modify_date:
        #the file must be (re)generated if was modified before the corresponding day was finished (i.e. it is incomplete)
        regenerate = modify_date < date + timedelta(days=1)

    if regenerate:
        print('generating %s' % filename)
    else:
        pass #print('skipping %s' %filename)

    return regenerate


# format date to string
def format_date(date, time = False, day = True, month = True):
    if not day:
        date_text = '%04u-%02u' % (date.year, date.month)
    elif not month:
        date_text = '%04u' % (date.year)
    else:
        date_text = '%04u-%02u-%02u' % (date.year, date.month, date.day)

    if time:
        date_text = '%s %02u:%02u:%02u' % (date_text, date.hour, date.minute, date.second)

    return date_text

# Fit a polynomial of given degree
def polyfit(y, deg = 1):
    x = np.arange(len(y))
    y = np.polyfit(x, y, deg)
    y = np.poly1d(y)
    y = [y(x) for x in x]
    return y


def get_years_from_csv(path, base):
    files = os.listdir(path)
    files = [f for f in files if f.startswith(base) and f.endswith('.csv')]
    files.sort()

    #base-year-month-day

    n = len(base) + 1
    year = int(files[0][n:n+4])
    end_year = int(files[-1][n:n+4])

    return year, end_year


# merge files with the same base filename and group by year, month
def Merge(path, base):

    print('Merging %s%s...' % (path, base))

    year, end_year = get_years_from_csv(path, base)


    for year in range(year, end_year + 1):

        filename = path + 'm_%s-%04u.csv' % (base, year)

        modify_date = get_modify_date(filename)
        next_year = datetime(year + 1, 1, 1)
        rebuild = not modify_date or modify_date < next_year

        if rebuild:
            with open(filename, 'w') as f_year:

                for month in range(1, 12+1):
                    filename = path + 'm_%s-%04u-%02u.csv' % (base, year, month)

                    modify_date = get_modify_date(filename)
                    next_month = next_year if month == 12 else datetime(year, month + 1, 1) 
                    rebuild = not modify_date or modify_date < next_month

                    if not rebuild:
                        with open(filename, 'r') as f: 
                            data = f.read()
                            f_year.write(data)
                            continue

                    with open(filename, 'w') as f_month:
                        for day in range(1, 31+1):
                            filename = path + '%s-%04u-%02u-%02u.csv' % (base, year, month, day)
                            if os.path.isfile(filename):
                                with open(filename, 'r') as f: 
                                    data = f.read()
                                    f_month.write(data)
                                    f_year.write(data)
                






# download the data from Fitbit
def Download(path, start_date):

    now = datetime.now()
    date = start_date

    while date < now:

        date_text = format_date(date)

        #download calories data
        csv_file = path + 'calories-%s.csv' % date_text
        if must_regenerate(csv_file, date):
            data = call_fitbit_api('https://api.fitbit.com/1/user/-/activities/calories/date/%s/1d/1min/time/00:00:00/23:59:59.json' % date_text)
            if data:
                rows = data['activities-calories-intraday']['dataset']
                with open(csv_file, 'wt') as f:
                    if rows:
                        for row in rows:
                            f.write('%s;%s;%s;%s;%s\n' % (date_text, row['time'], row['level'], row['mets'], row['value']))


        #download heart data
        csv_file = path + 'heart-%s.csv' % date_text
        if must_regenerate(csv_file, date):
            data = call_fitbit_api('https://api.fitbit.com/1/user/-/activities/heart/date/%s/1d/1sec/time/00:00:00/23:59:59.json' % date_text)
            if data:
                rows = data['activities-heart-intraday']['dataset']
                with open(csv_file, 'wt') as f:
                    if rows:
                        for row in rows:
                            f.write('%s;%s;%s\n' % (date_text, row['time'], row['value']))

        #download sleep data
        csv_file = path + 'sleep-%s.csv' % date_text
        if must_regenerate(csv_file, date):
            data = call_fitbit_api('https://api.fitbit.com/1.2/user/-/sleep/date/%s.json' % date_text)
            if data:
                data = data['sleep']
                with open(csv_file, 'wt') as f:
                    if data:
                        for sleep in data:
                            sleep_type = sleep['type']
                            rows = sleep['levels']['data']
                            for row in rows:
                                dt = datetime.fromisoformat(row['dateTime'])
                                tm = '%02u:%02u:%02u' % (dt.hour, dt.minute, dt.second)
                                dt = format_date(dt)

                                f.write('%s;%s;%s;%s;%s\n' % (dt, tm, row['level'], row['seconds'], sleep_type))

                    #make sure the file is sorted by date/time (not always the case as the sleep types are grouped together first)
                    with open(csv_file, 'rt') as f: data = f.read()
                    data = data.split('\n')
                    data.sort()
                    with open(csv_file, 'wt') as f: 
                        for row in data:
                            if row:
                                f.write(row + '\n')
            
        date += timedelta(days=1)



def newfig(title):
    fig = plt.figure(figsize=(20,10), dpi=100)  
    fig.suptitle(title)
    return fig


def setup_axes(fig, date, end_date, ylim):
    plt.ylabel('BPM')
    plt.legend()

    axes = fig.axes[0]
    
    axes.grid(True, linestyle='--', which='major')
    axes.grid(True, linestyle=':', which='minor')
    axes.tick_params(axis='x', which='major', pad=20)
    axes.tick_params(axis='y', labelright = True)

    axes.set_xlim(date, end_date)

    axes.set_ylim(ylim[0], ylim[1])
    axes.set_yticks(range(ylim[0], ylim[1], 5), minor=False)

    return axes

def setup_xticks(axes, date, end_date, minor = False, td = timedelta(days=1), label = lambda date: format_date(date)):
    xticks, labels = [], []
    while(date <= end_date):
        xticks.append(date2num(date))
        labels.append(label(date))
        date += td

    axes.set_xticks(xticks, minor=minor)
    axes.set_xticklabels(labels, minor=minor)


def savefig(fig, path, base, points):
    fig.canvas.draw()

    print('saving %s (%u points)..' % (base, points))
    plt.savefig(path + 'heart-' + base + '.png', pad_inches = 0.5, bbox_inches = 'tight')

    fig.clear()


# read the first columns of a CSV (date/time and value) 
def read_csv(path, base, year):
    dates = []
    values = []
    data = open(path + '%s-%u.csv' % (base, year), 'rt').read()
    rows = data.split('\n')
    for row in rows:
        if row:
            cols = row.split(';')

            date = datetime.fromisoformat('%s %s' % (cols[0], cols[1]))
            value = int(cols[2])

            dates.append(date)
            values.append(value)

    return dates, values


# group and average the given dates/values per given minutes
def average(dates, values, minutes):
    dates_a, values_a = [], []

    date = dates[0]
    date = date.replace(second = 0, microsecond = 0)

    i = 0 
    while i < len(dates):

        next_date = date + timedelta(minutes=minutes)

        _sum, j = 0, i
        while i < len(dates) and dates[i] < next_date:
            _sum += values[i]
            i += 1

        if i > j:
            dates_a.append(date)
            values_a.append(round(_sum / (i - j)))

        date = next_date


    return dates_a, values_a




def Graph(path, name):
    year, end_year = get_years_from_csv(path, 'calories')

    for year in range(year, end_year + 1):
        print('loading %u...' % year)

        # read activity levels
        activity_dates, activity_levels = read_csv(path, 'm_calories', year)

        # read heart rate values
        dates, values = read_csv(path, 'm_heart', year)
        # average to 1 min values        
        dates, values = average(dates, values, 1)

        # associate activity levels and resting rates
        levels = []
        resting_rate = []
        resting_rate_dates = []
        last_resting_date = None

        i = 0
        for date, value in zip(dates, values):
                # find corresponding activity
                while activity_dates[i] < date: i = i+1

                level = activity_levels[i]
                levels.append(level)

                # only count as a resting rate if inactive for at least 5 min
                if level == 0:
                    if last_resting_date is None: 
                        last_resting_date = date
                    elif (date - last_resting_date).total_seconds() > 5 * 60:
                        resting_rate.append(value)
                        resting_rate_dates.append(date)
                else:
                    last_resting_date = None


        # calculate averages 
        heart_60min_dates, heart_60min = average(dates, values, 60)
        resting_rate_60min_dates, resting_rate_60min = average(resting_rate_dates, resting_rate, 60)


        print('graphing...')



        # calculate activity colors 
        activity_colors = []
        activity_offset = 45   # where on the Y axis the activity level is displayed in the weekly chart
        base_colors = ['lightblue', 'darkblue', 'indianred', 'darkred'] # color used for each activity level

        for i, level in enumerate(activity_levels):
            activity_levels[i] += activity_offset
            activity_colors.append(base_colors[level])


        # draw weekly graph
        start_date = activity_dates[0]

        i = j = 0
        k = l = 0
        p = q = 0
        r = s = 0

        date = start_date
        while i < len(dates):
            #print(date)

            cur_date = date
            end_date = date + timedelta(days=7)

            while j < len(dates) and dates[j] < end_date: j += 1
            while l < len(activity_dates) and activity_dates[l] < end_date: l += 1
            while q < len(heart_60min_dates) and heart_60min_dates[q] < end_date: q += 1
            while s < len(resting_rate_60min_dates) and resting_rate_60min_dates[s] < end_date: s += 1

            date_fmt = format_date(date)

            if must_regenerate(path + 'heart-' + date_fmt + '.png', end_date):

                fig = newfig('Heart Rate %s %s / 7 days' % (name, date_fmt))

                plt.plot(dates[i:j], values[i:j], label='1 min heart rate')

                x = heart_60min_dates[p:q]
                y = heart_60min[p:q]
                plt.plot(x, y, label='60 min average')
                y = polyfit(y)
                plt.plot(x, y, label='trend')


                x = resting_rate_60min_dates[r:s]
                y = resting_rate_60min[r:s]
                plt.plot(x, y, label='60 min resting average')
                y = polyfit(y)
                lines = plt.plot(x, y, label='trend')
                plt.scatter(x, y, color = lines[0].get_color())


                plt.scatter(activity_dates[k:l], activity_levels[k:l], s=1, c=activity_colors[k:l], marker='.', label='1 min activity level')

                
                # setup axes and ticks
                axes = setup_axes(fig, cur_date, end_date, [40, 150])
                setup_xticks(axes, cur_date, end_date)
                setup_xticks(axes, cur_date, end_date, minor = True, td = timedelta(hours=4), label = lambda date: str(date.hour))


                # draw and save
                savefig(fig, path, date_fmt, j - i)

            i = j
            k = l
            p = q
            r = s
            date = end_date



        # draw monthly graph
        i = 0
        k = 0
        while i < len(heart_60min_dates):
            date = heart_60min_dates[i]
            #print(date)

            cur_date = datetime(date.year, date.month, 1)
            end_date = datetime(date.year + 1, 1, 1) if date.month == 12 else datetime(date.year, date.month + 1, 1)

            j = i
            while j < len(heart_60min_dates) and heart_60min_dates[j].month == date.month : j += 1

            l = k
            while l < len(resting_rate_60min_dates) and resting_rate_60min_dates[l].month == date.month : l += 1

            date_fmt = format_date(date, day=False)
            
            if must_regenerate(path + 'heart-' + date_fmt + '.png', end_date):
                fig = newfig('Heart Rate %s %s' % (name, date_fmt))

                y = heart_60min[i:j]
                plt.plot(heart_60min_dates[i:j], y, label='60 min average')
                y = polyfit(y)
                plt.plot(heart_60min_dates[i:j], y, label='trend')


                y = resting_rate_60min[k:l]
                plt.plot(resting_rate_60min_dates[k:l], y, label='60 min resting average')
                y = polyfit(y)
                plt.plot(resting_rate_60min_dates[k:l], y, label='trend')
                
                # setup axes and ticks
                axes = setup_axes(fig, cur_date, end_date, [50, 120])
                setup_xticks(axes, cur_date, end_date, td = timedelta(days=2))
                setup_xticks(axes, cur_date, end_date, minor = True, td = timedelta(hours=8), label = lambda date: str(date.hour))


                # draw and save
                savefig(fig, path, date_fmt, j - i)

            i = j
            k = l



        # draw yearly graph
        cur_date = datetime(date.year, 1, 1)
        end_date = datetime(date.year + 1, 1, 1)

        date = datetime(year, 1, 1)
        date_fmt = format_date(date, month=False)

        if must_regenerate(path + 'heart-' + date_fmt + '.png', end_date):
            fig = newfig('Heart Rate %s %s' % (name, date_fmt))

            y = polyfit(heart_60min, deg = 1)
            plt.plot(heart_60min_dates, y, label='60 min average trend')

            y = polyfit(resting_rate_60min, deg = 1)
            plt.plot(resting_rate_60min_dates, y, label='60 min resting average trend')


            # setup axes and ticks
            axes = setup_axes(fig, cur_date, end_date, [50, 120])
            setup_xticks(axes, cur_date, end_date, td = timedelta(days=31), label = lambda date: format_date(date, day = False))
            setup_xticks(axes, cur_date, end_date, minor = True, td = timedelta(days=7), label = lambda date: str(date.day))


            # draw and save
            savefig(fig, path, date_fmt, len(heart_60min))




if __name__ == '__main__':

    #python fitbit.py <path> <name> <starting_date> <token>

    #path: where to download the csv / save the graphs (ends with a slash)
    #name: name that will be displayed in the graphs
    #starting_date: the date from which the data will be reguested: yyyy-mm-dd
    #token: OAuth token generated on https://dev.fitbit.com/apps see OAuth 2.0 tutorial page after creating an app (use 31536000 for a 1-year token)
    

    path = sys.argv[1]
    date = datetime.fromisoformat(sys.argv[2])

    # always starts on a Monday
    date -= timedelta(days = date.weekday())

    name = sys.argv[3]

    token = sys.argv[4]

    if len(sys.argv)>5: debug = (sys.argv[5] == 'True')


    Download(path, date)

    Merge(path, 'calories')
    Merge(path, 'sleep')
    Merge(path, 'heart')



    Graph(path, name)
