from pprint import pprint
from requests import post
import json
import os
from time import time
import cloudant

comment_threshold = 10
max_iterations = 2  # number of iterations that should run; -1 to keep going until all issues/prs fetched
# first in each tuple is
pull_rates = [(100, 3), (90, 7), (80, 9), (70, 12), (60, 15), (50, 20), (40, 25), (30, 35),
              (25, 50), (20, 60), (18, 68), (16, 75), (14, 80), (12, 95), (10, 100)]


# for timing how long it takes a function to run
def time_execution(function):
    def wrapper(*args):
        print(f"Timing {function.__name__}")

        start_time = time()
        value = function(*args)
        end_time = time()

        print(f"{function.__name__} took {round(end_time - start_time, 3)} seconds to run")
        return value

    return wrapper


@time_execution
def run_query(auth, owner, repo, pull_type, db_name):
    print(f"Gathering {pull_type}...")
    cloudant.createDatabase(db_name)

    # final list to be returned
    json_list = []
    # stores the authorisation token and accept
    headers = {
        "Authorization": "token " + auth,
        "Accept": "application/vnd.github+json",
    }

    # for pagination
    has_next_page = True
    cursor = None
    above_threshold = True

    # initial pull rate is (12, 100)
    pr_index = -1

    i = 0
    # query can only fetch at most 100 at a time, so keeps fetching until all fetched
    while has_next_page and above_threshold and i != max_iterations:
        i += 1

        # forms the query and performs call, on subsequent iterations passes in cursor for pagination
        query = get_comments_query(repo, owner, pull_type, pull_rates[pr_index], cursor)
        try:
            request = post("https://api.github.com/graphql", json={"query": query}, headers=headers)
        except Exception:
            print(f"error at iteration {i}")
            i -= 1
            continue
        # temp = request.json()

        # if api call was successful, adds the comment to the comment list
        if request.status_code == 200:
            try:
                # trims the result of the api call to remove unneeded nesting
                trimmed_request = request.json()["data"]["repository"][pull_type]
            except TypeError:
                if json_list is not None:
                    pprint(json_list)
                print("Invalid information provided")
                break
            # pprint(trimmed_request)

            # determines if all issues/prs have been fetched
            has_next_page = trimmed_request["pageInfo"]["hasNextPage"]
            if has_next_page:
                cursor = trimmed_request["pageInfo"]["endCursor"]

            # checks if any of the issues/prs have fewer than threshold comments
            # if so, remove them and don't fetch any more
            last_count = trimmed_request["edges"][-1]["node"]["comments"]["totalCount"]
            if last_count < comment_threshold:
                above_threshold = False
                for node in reversed(trimmed_request["edges"]):
                    if node["node"]["comments"]["totalCount"] < comment_threshold:
                        trimmed_request["edges"].pop()
                    else:
                        break
            else:
                # determine the pull rate for the next iteration
                for j, rate in enumerate(pull_rates):
                    if last_count <= rate[1]:
                        pr_index = j
                        break

            # loop through issues/prs
            for j, edge in enumerate(trimmed_request["edges"]):
                # filter out comments made by bots
                node = edge["node"]
                node["comments"]["edges"] = filter_comments(node["comments"]["edges"])

                # update the totalCount
                count = len(node["comments"]["edges"])
                node["comments"]["totalCount"] = count

                # pull the rest of the comments if there are any
                if node["comments"]["pageInfo"]["hasNextPage"]:
                    comments = get_other_comments(node["number"], repo, owner, pull_type[0:-1],
                                                  headers, node["comments"]["pageInfo"]["endCursor"])

                    # add comments to exiting ones, update totalCount, if under threshold comments, remove
                    if count + len(comments) >= comment_threshold:
                        node["comments"]["edges"] += comments
                        node["comments"]["totalCount"] += len(comments)
                        node["comments"].pop("pageInfo")
                    else:
                        trimmed_request["edges"].pop(j)

                cloudant.addDocument(node, db_name)

            json_list += trimmed_request["edges"]  # add to final list
            print(f'{len(json_list)} {pull_type} gathered')  # print progress

        else:
            print(f"Status code: {str(request.status_code)} on iteration {i}, pr_index = {pr_index}. Retrying")
            i -= 1

    # write to file
    json_string = json.dumps(json_list, indent=4)
    write_to_file(json_string, repo, pull_type)
    # pprint(json_string)
    return json_string


# gets comments for an issue/pr
def get_other_comments(number, repo, owner, p_type, headers, cursor=None):  # todo try getting multiple comments at once

    # for pagination
    has_next_page = True
    comment_list = None

    # query can only fetch at most 100 at a time, so keeps fetching until all fetched
    while has_next_page:

        # forms the query and performs call, on subsequent iterations passes in cursor for pagination
        query = get_ind_query(repo, owner, number, p_type, cursor)
        request = post("https://api.github.com/graphql", json={"query": query}, headers=headers)

        # if api call was successful, adds the comment to the comment list
        if request.status_code == 200:
            # trims the result of the api call to remove unneeded nesting
            # pprint(request.json())
            temp = request.json()
            try:
                comments = request.json()["data"]["repository"][p_type]["comments"]
            except TypeError:
                print("Invalid information provided")
                break
            except KeyError:
                print("error while pulling comments")
                break
            # pprint(trimmed_request)

            # determines if all comments have been fetched
            has_next_page = comments["pageInfo"]["hasNextPage"]
            if has_next_page:
                cursor = comments["pageInfo"]["endCursor"]

            filtered_comments = filter_comments(comments["edges"])

            # add to list
            if comment_list is None:
                comment_list = filtered_comments
            else:
                comment_list += filtered_comments
        else:
            print(f"Status code: {str(request.status_code)} while fetching comments. Retrying")

    return comment_list


# filter out any comments made by bots
def filter_comments(comment_list):
    return_list = []
    # iterates through each comment removes it if it was made by a bot
    for comment in comment_list:
        try:
            if comment["node"]["author"]["__typename"] != "Bot":
                return_list.append(comment)
        except TypeError:
            # if account deleted, author will be None so give it login deletedUser
            comment["node"]["author"] = {'login': 'deletedUser'}

    return return_list


# writes a json_string out to a file
def write_to_file(json_string, repo, p_type):
    cwd = os.getcwd()
    filepath = cwd + "/fetched_data"
    if not os.path.exists(filepath):
        os.makedirs(filepath)
    # writing data into repoName_pullType.json in cwd/fetched_data directory
    with open(filepath + "/" + f"{repo}_{p_type}.json", "w") as outfile:
        outfile.write(json_string)


# returns query for issue or pull request comments
def get_comments_query(repo, owner, p_type, pull_rate, cursor=None):
    # for pagination
    if cursor is not None:
        start_point = f', after: "{cursor}"'
    else:
        start_point = ""

    query = """
        {
            repository(name: "%s", owner: "%s") {
                %s(first:%d, orderBy:{field: COMMENTS, direction: DESC}%s) {
                    edges {
                        node {
                            number
                            title
                            author {
                                login
                            }
                            state
                            closedAt
                            comments(first: %d) {
                                totalCount
                                edges {
                                    node {
                                        author {
                                            login
                                            __typename
                                        }
                                        bodyText
                                        createdAt
                                    }
                                }
                                pageInfo {
                                    hasNextPage
                                    endCursor
                                }
                            }
                        }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
        }
        """ % (repo, owner, p_type, pull_rate[0], start_point, pull_rate[1])

    return query


# returns query for individual comments
def get_ind_query(repo, owner, number, p_type, cursor=None):
    # for pagination
    if cursor is not None:
        start_point = f', after: "{cursor}"'
    else:
        start_point = ""

    query = """
    {
        repository(name: "%s", owner: "%s") {
            %s(number: %d) {
                comments(first:100%s) {
                    edges {
                        node {
                            author {
                                login
                                __typename
                            }
                            bodyText
                            createdAt
                        }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
        }  
    }
    """ % (repo, owner, p_type, number, start_point)

    return query


# main function for testing code
if __name__ == '__main__':

    print("Enter an access token: ", end="")
    auth = input()

    pull_type = ""
    valid = False

    while not valid:
        print("Enter a repo (owner/repo): ", end="")
        owner_repo = input().split("/")
        if len(owner_repo) != 2:
            print("Invalid input")
        else:
            print("Get issues or pull requests? (i or p): ", end="")
            letter = input()

            if letter == "i":
                pull_type = "issues"
                valid = True
            elif letter == "p":
                pull_type = "pullRequests"
                valid = True
            else:
                print("Invalid input")

    database = f"{owner_repo[0]}/{owner_repo[1]}-{pull_type}"
    if cloudant.checkDatabases(database):
        print(f"{owner_repo[0]}/{owner_repo[1]}-{pull_type} is already in the database. Use existing data? (y/n): "
              , end="")
        valid = False

        while not valid:
            ans = input()
            if ans == 'y':
                print("Running analysis on existing data")
                valid = True
            elif ans == 'n':
                result = run_query(auth, owner_repo[0], owner_repo[1], pull_type, database)
                valid = True
            else:
                print("Invalid input. Use existing data? (y/n): ")

    else:
        result = run_query(auth, owner_repo[0], owner_repo[1], pull_type, database)
