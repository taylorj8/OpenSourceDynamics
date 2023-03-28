import json, requests, os, csv
import statistics
from time import time
from ibm_watson import NaturalLanguageUnderstandingV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from ibm_watson.natural_language_understanding_v1 import Features, SentimentOptions, EmotionOptions
from pprint import pprint
from query import run_query, write_to_file
import scipy.stats as stats

# Pulls API Keys from keys.txt file
keys = open('keys.txt', 'r')
api_key = keys.readline().rstrip('\n')
url = keys.readline().strip('\n')
keys.close()
if api_key == 'apikey' or url == 'url':
    print('ERROR: need to put api key in keys.txt file')

# IBM NLU authentication
authenticator = IAMAuthenticator(api_key)
natural_language_understanding = NaturalLanguageUnderstandingV1(
    version='2022-04-07',
    authenticator=authenticator
)
natural_language_understanding.set_service_url(url)


# Defines repositories as objects
class Repository:
    def __init__(self, data):
        # Creat list of PullRequest objects
        self.pull_requests = list_of_pr(data)

        # Defines values for state and gender
        self.values_state = ['Merged', 'Closed', 'Open']
        self.values_gender = ['Female', 'Male', 'Unknown']

        # Calculate averages
        self.average_sentiment = average(self.pull_requests, 'Sentiment', 'None')[0]
        self.average_sentiment_state = average(self.pull_requests, 'Sentiment', 'State')
        self.average_sentiment_gender = average(self.pull_requests, 'Sentiment', 'Gender')
        em_av = [average(self.pull_requests, 'Sadness', 'None'), 
                                  average(self.pull_requests, 'Joy', 'None'),
                                  average(self.pull_requests, 'Fear', 'None'),
                                  average(self.pull_requests, 'Disgust', 'None'),
                                  average(self.pull_requests, 'Anger', 'None')]
        self.average_emotion = [em_av[0][0], em_av[1][0], em_av[2][0], em_av[3][0], em_av[4][0]]
        self.average_emotion_state = [average(self.pull_requests, 'Sadness', 'State'), 
                                  average(self.pull_requests, 'Joy', 'State'),
                                  average(self.pull_requests, 'Fear', 'State'),
                                  average(self.pull_requests, 'Disgust', 'State'),
                                  average(self.pull_requests, 'Anger', 'State')]
        self.average_emotion_gender = [average(self.pull_requests, 'Sadness', 'Gender'), 
                                  average(self.pull_requests, 'Joy', 'Gender'),
                                  average(self.pull_requests, 'Fear', 'Gender'),
                                  average(self.pull_requests, 'Disgust', 'Gender'),
                                  average(self.pull_requests, 'Anger', 'Gender')]

        # Calculate frequencies
        self.freq_state = frequency(self.pull_requests, 'State')
        self.freq_gender = frequency(self.pull_requests, 'Gender')

        # Calculatte correlation
        self.corr_state_gender = chi_square_correlation_test(self.pull_requests)
        self.corr_state_comments = None
        self.corr_state_sentiment = point_biserial_correlation_test(self.pull_requests, 'State', 'Sentiment')
        self.corr_state_emotion = [point_biserial_correlation_test(self.pull_requests, 'State', 'Sadness'),
                                   point_biserial_correlation_test(self.pull_requests, 'State', 'Joy'),
                                   point_biserial_correlation_test(self.pull_requests, 'State', 'Fear'),
                                   point_biserial_correlation_test(self.pull_requests, 'State', 'Disgust'),
                                   point_biserial_correlation_test(self.pull_requests, 'State', 'Anger')]
        self.corr_gender_comments = None
        self.corr_gender_sentiment = point_biserial_correlation_test(self.pull_requests, 'Gender', 'Sentiment')
        self.corr_gender_emotion = [point_biserial_correlation_test(self.pull_requests, 'Gender', 'Sadness'),
                                   point_biserial_correlation_test(self.pull_requests, 'Gender', 'Joy'),
                                   point_biserial_correlation_test(self.pull_requests, 'Gender', 'Fear'),
                                   point_biserial_correlation_test(self.pull_requests, 'Gender', 'Disgust'),
                                   point_biserial_correlation_test(self.pull_requests, 'Gender', 'Anger')]
        self.corr_comments_sentiment = None
        self.corr_comments_emotion = None


        # Preform Point Biserial test
        self.p_value = self.r_value = None
        #if self.merged_average is not None and self.closed_average is not None:
        #point_biserial = correlation_test(self.pull_requests)
        #self.p_value = round(point_biserial.pvalue, 4)
        #self.r_value = round(point_biserial.statistic, 4)
    
    def to_csv(self):
        cwd = os.getcwd()
        csv_fields = ['Number', 'Title', 'Author', 'Gender', 'State', 'Created', 'Closed', 'Number of Comments', 'Sentiment', 'Sadness', 'Joy', 'Fear', 'Disgust', 'Anger']
        with open(f'{cwd}/fetched_data/sentiment_analysis_result.csv', 'w', newline='') as analysis_results_file:
            writer = csv.DictWriter(analysis_results_file, csv_fields)
            writer.writeheader()
            for pr in self.pull_requests:
                analysis_result = [
                    {
                        'Number': f'{str(pr.number)}',
                        'Title': f'{str(pr.title)}',
                        'Author': f'{str(pr.author)}',
                        'Gender': f'{str(pr.gender)}',
                        'State': f'{str(pr.state)}',
                        'Created': f'{str(pr.createdAt)}',
                        'Closed': f'{str(pr.closedAt)}',
                        'Number of Comments': f'{str(pr.number_of_comments)}',
                        'Sentiment': f'{str(pr.sentiment)}',
                        'Sadness': f'{str(pr.emotion[0][1])}',
                        'Joy': f'{str(pr.emotion[1][1])}',
                        'Fear': f'{str(pr.emotion[2][1])}',
                        'Disgust': f'{str(pr.emotion[3][1])}',
                        'Anger': f'{str(pr.emotion[4][1])}'
                    }
                ] 
                writer.writerows(analysis_result)

    def stats_to_csv(self):
        cwd = os.getcwd()
        csv_fields = ['Sentiment Average', 'Emotion Averages', 
                      'State Values', 'State Frequency', 'State-Sentiment Average', 'State-Emotion Averages',
                      'Gender Values', 'Gender Frequency', 'Gender-Sentiment Average', 'Gender-Emotion Averages',
                      'Correlation', 'State-Gender Correlation', 'State-Comments Correlation', 'State-Sentiment Correlation', 'State-Emotion Correlations',
                      'Gender-Comments Correlation', 'Gender-Sentiment Correlation', 'Gender-Emotion Correlations', 'Comments-Sentiment Correlation', 'Comments-Emotion Correlation']
        with open(f'{cwd}/fetched_data/sentiment_analysis_statistics_result.csv', 'w', newline='') as analysis_results_file:
            writer = csv.DictWriter(analysis_results_file, csv_fields)
            writer.writeheader()
            for i in range(3):
                analysis_result = [
                    {
                        'Sentiment Average': f'{str(self.average_sentiment) if i == 0 else ""}',
                        'Emotion Averages': f'{str(self.average_emotion) if i == 0 else ""}',
                        'State Values': f'{self.values_state[i]}',
                        'State Frequency': f'{str(self.freq_state[i])}',
                        'State-Sentiment Average': f'{str(self.average_sentiment_state[i])}', 
                        'State-Emotion Averages': f'{str([self.average_emotion_state[0][i], self.average_emotion_state[1][i], self.average_emotion_state[2][i], self.average_emotion_state[3][i], self.average_emotion_state[4][i]])}',
                        'Gender Values': f'{self.values_gender[i]}', 
                        'Gender Frequency': f'{str(self.freq_gender[i])}', 
                        'Gender-Sentiment Average': f'{str(self.average_sentiment_gender[i])}', 
                        'Gender-Emotion Averages': f'{str([self.average_emotion_gender[0][i], self.average_emotion_gender[1][i], self.average_emotion_gender[2][i], self.average_emotion_gender[3][i], self.average_emotion_gender[4][i]])}',
                        'Correlation': f'{"p-value" if i == 0 else "test statistic" if i == 1 else ""}',
                        'State-Gender Correlation': f'{self.corr_state_gender[i] if i != 2 else ""}',
                        'State-Comments Correlation': f'{"?"}',
                        'State-Sentiment Correlation': f'{self.corr_state_sentiment[i] if i != 2 else ""}',
                        'State-Emotion Correlations': f'{self.corr_state_emotion[i] if i != 2 else ""}',
                        'Gender-Comments Correlation': f'{"?"}',
                        'Gender-Sentiment Correlation': f'{self.corr_gender_sentiment[i] if i != 2 else ""}',
                        'Gender-Emotion Correlations': f'{self.corr_gender_emotion[i] if i != 2 else ""}',
                        'Comments-Sentiment Correlation': f'{"?"}',
                        'Comments-Emotion Correlation': f'{"?"}'
                    }
                ] 
                writer.writerows(analysis_result)            

    def __str__(self):
        result = ''
        # Print PullRequests
        for pr in self.pull_requests:
            result += str(pr) + '\n'
        result += '\n'

        # Print averages
        result += str(self.average_sentiment) + '\n'
        result += str(self.average_sentiment_state) + '\n'
        result += str(self.average_sentiment_gender) + '\n'
        result += str(self.average_emotion) + '\n'
        result += str(self.average_emotion_state) + '\n'
        result += str(self.average_emotion_gender) + '\n'

        # Print frequencies
        result += str(self.freq_state) + '\n'
        result += str(self.freq_gender) + '\n\n'

        # Print correlation
        if self.p_value is None:
            result += 'Can not preform a correlation test\n'
        else:
            result += 'State and sentiment are '
            if self.p_value > 0.05:
                result += 'not '
            result += 'statistically significant: p-value of ' + str(self.p_value) + ' and R-value of ' + str(
                self.r_value)

        return result

# Defines pull requests as objects
class PullRequest:
    # Constructor takes in a json node representing a pr
    def __init__(self, pr):
        self.number = pr['number']
        self.title = pr['title']
        self.closedAt = pr['closedAt']
        self.createdAt = pr['createdAt']
        self.state = pr['state']
        self.number_of_comments = pr['commentCount']
        self.author = pr['author'].split()[0]
        self.gender = getGender(self.author)

        # NEEDS TO CHANGE
        # Takes all comments and concatenates into single string -> not efficient
        comments = ''
        for comment in pr['comments']:
            comments += comment['bodyText'] + ' '
        self.comments = comments

        # IBM NLP
        response = natural_language_understanding.analyze(
            text=self.comments,
            features=Features(sentiment=SentimentOptions(), emotion=EmotionOptions())).get_result()
        # print(response)
        self.sentiment = round(response['sentiment']['document']['score'], 4)
        # Creates an array to store emotion scores
        self.emotion = [['sadness', 0], ['joy', 0], ['fear', 0], ['disgust', 0], ['anger', 0]]
        for i in range(5):
            self.emotion[i][1] = round(response['emotion']['document']['emotion'][self.emotion[i][0]], 4)
        
        # print(self.emotion)
        # self.main_emotion = max(self.emotion)
        # self.s = ""
        # for i in range(5):
        #    self.s += self.emotion[i][0] + ": " + self.emotion[i][1] + "\n"

    # Defines a print method for pr
    def __str__(self):
        #s = str(self.emotion)
        return "<state: " + self.state + "; comments: " + str(self.number_of_comments) + "; sentiment: " + str(
            self.sentiment) + "; author: " + self.author + "; gender: " + self.gender + ">"

# Takes a json file and parses it into a list of PullRequest objectss
def list_of_pr(data):
    pull_requests = []
    for pr in data:
        # NEED TO IMPLEMENT BETTER ERROR HANDLING
        # ApiException: Error: not enough text for language id, Code: 422
        try:
            pull_requests.append(PullRequest(pr))
        except Exception:
            pass
    return pull_requests

# Get averages for different variables and filters
def average(pull_requests, variable, filter):
    list1 = []
    list2 = []
    list3 = []

    for pr in pull_requests:
        filter_var = ''
        if (filter == 'State'):
            filter_var = pr.state
        elif (filter == 'Gender'):
            filter_var = pr.gender
        if filter == 'None':
            filter_var = 'None'

        if variable == 'Sentiment':
            var = pr.sentiment
        elif variable == 'Sadness':
            var = pr.emotion[0][1]
        elif variable == 'Joy':
            var = pr.emotion[1][1]
        elif variable == 'Fear':
            var = pr.emotion[2][1]
        elif variable == 'Disgust':
            var = pr.emotion[3][1]
        elif variable == 'Anger':
            var = pr.emotion[4][1]
        
        if filter_var == 'MERGED' or filter_var == 'female' or filter_var == 'None':
            list1.append(var)
        elif filter_var == 'CLOSED' or filter_var == 'male':
            list2.append(var)
        else:
            list3.append(var)
    
    return [None if not list1 else round(statistics.fmean(list1), 4), 
            None if not list2 else round(statistics.fmean(list2), 4),
            None if not list3 else round(statistics.fmean(list3), 4)]

# Get frequencies for different variables
def frequency(pull_requests, variable):
    list = [0, 0, 0]
    for pr in pull_requests:
        var = ''
        if (variable == 'State'):
            var = pr.state
        elif (variable == 'Gender'):
            var = pr.gender
        
        if var == 'MERGED' or var == 'female':
            list[0] += 1
        elif var == 'CLOSED' or var == 'male':
            list[1] += 1
        else:
            list[2] += 1
    
    return list

# Preforms a Point-Biserial Correlation test and prints the result
def point_biserial_correlation_test(pull_requests, di_var, cont_var):
    di_list = []
    cont_list = []
    for pr in pull_requests:
        di_value = ''
        if di_var == 'State':
            di_value = pr.state
        elif di_var == 'Gender':
            di_value = pr.gender
        

        if di_value == 'MERGED' or di_value == 'female':
            di_list.append(0)
        elif di_value == 'CLOSED' or di_value == 'male':
            di_list.append(0)
        else:
            continue

        if cont_var == 'Sentiment':
            cont_list.append(pr.sentiment)
        elif cont_var == 'Sadness':
            cont_list.append(pr.emotion[0][1])
        elif cont_var == 'Joy':
            cont_list.append(pr.emotion[1][1])
        elif cont_var == 'Fear':
            cont_list.append(pr.emotion[2][1])
        elif cont_var == 'Disgust':
            cont_list.append(pr.emotion[3][1])
        elif cont_var == 'Anger':
            cont_list.append(pr.emotion[4][1])

    result = stats.pointbiserialr(di_list, cont_list)
    return [result.pvalue, result.statistic]

# Preforms a Chi-Square Correlation test and prints the result
def chi_square_correlation_test(pull_requests):
    list = [[0, 0], [0, 0], [0, 0]]
    for pr in pull_requests:
        if pr.gender == 'female':
            if pr.state == 'MERGED':
                list[0][0] += 1
            elif pr.state == 'CLOSED':
                list[0][1] += 1
        elif pr.gender == 'male':
            if pr.state == 'MERGED':
                list[1][0] += 1
            elif pr.state == 'CLOSED':
                list[1][1] += 1
        else:
            if pr.state == 'MERGED':
                list[2][0] += 1
            elif pr.state == 'CLOSED':
                list[2][1] += 1
    result = stats.chi2_contingency(list)
    return [result.pvalue, result.statistic]

# Predicts gender of a given name using genderize.io API
def getGender(name):
	url = ""
	cnt = 0
        
	if url == "":
		url = "name[0]=" + name
	else:
		cnt += 1
		url = url + "&name[" + str(cnt) + "]=" + name

	req = requests.get("https://api.genderize.io?" + url)
	result = json.loads(req.text)
	gender = result[0]["gender"]
	if gender is None:
		return "none"
	return gender