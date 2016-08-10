from py2neo import authenticate, Graph
from py2neo import Node, Relationship
from py2neo import error
from lxml import html
import requests

import difflib
import operator

import nltk, re
from nltk.parse import stanford

import wit, json, requests
access_token = 'F4BZT33ZTYD5LNVFUECHOMNUOYGUNCFK'
wit.init()

user_name = ""
user_session = {'budget':None, 'search_intent':None, 'bed_rooms':None, 'area':None}

def property_images_in_chat():
    global listing_url
    url = listing_url
    page = requests.get(url)
    tree = html.fromstring(page.text)
    res = tree.xpath('//div[@class="row listing"]/div[1]/@style')[:3]
    urls = []
    for each in res:
        clean_url = re.findall(r'\((.*)\)',each)
        urls.append("".join(clean_url))
    html_str ="<table><tr>"
    for index, each_url in enumerate(urls):
        html_str += "<td><img src='"+each_url+"'>&nbsp;&nbsp;<br />To Shortlist this property type : "+str(index+1)+"</td>"
    html_str+="</tr></table>"
    return html_str

def reply_back_now(entity=None):
    if entity=='budget':
        return 'You have not specified your budget. Please tell me your budget like 10000-12000'
    if entity=='search_intent':
        return 'Are you looking for to rent or to buy ??'
    if entity=='room_type':
        return "Can you tell me if you are looking for 2 BHK's or 3 BHK's or any other choice ?"
    if entity=='area':
        return "Can you please specify any area you are looking for ?"

def main_parse(text, entity=None):
    global user_session

    if entity=='budget':
        ret = budget_parse(text)
        user_session['min_inr'] = ret[0]
        user_session['max_inr'] = ret[1]
        user_session['budget'] = 'has been set'
        #print user_session,"from main_parse"
        
    elif entity=='search_intent':
        ret = search_intent_parse(text)
        user_session['search_intent'] = ret

    elif entity=='room_type':
        ret = room_type_parse(text)
        user_session['bed_rooms'] = ret
    elif entity=='area':
        ret = area_parse(text)
        user_session['area'] = ret

def room_type_parse(room_type):
    if 'one' in room_type:
        return 1
    elif 'two' in room_type:
        return 2
    elif 'three' in room_type:
        return 3
    elif 'one room' in room_type:
        return 0.5

def search_intent_parse(text):
    if 'rent' in text:
        return 'rent'
    else:
        return 'sale'

def budget_parse(text):
    if '-' in text:
        min_inr, max_inr = text.split('-')
    return (min_inr, max_inr)


def area_parse(text):
    base_url = "http://www.commonfloor.com/autosuggest.php?item=location&c=Bangalore&str=" + text
    r = requests.get(base_url)
    res = json.loads(r.text)
    if len(res)>0:
        user_session['area_code'] = res[0].split('|')[-1]
        return res[0].split('~')[0]

    else:
        base_url = "http://www.commonfloor.com/autosuggest.php?item=location&c=Bangalore&str=" + text[0:4]
        r = requests.get(base_url)
        res = json.loads(r.text)
        if len(res)>0:
            print "Did you mean ? "+str(res[0].split('~')[0])
            user_input = raw_input()
            if 'ye' in user_input:
                user_session['area_code'] = res[0].split('|')[-1]
                return res[0].split('~')[0]
        return None

def wiki_call(query):
    try:
        array = wikipedia.search(query)
        if len(array) > 0:
          var = wikipedia.summary(array[0], sentences = 3)
          var = var.encode('ascii','ignore')
          #k = re.sub(r'\([^)]*\)', '',var)
          #word1 = " ".join(re.findall("[a-zA-Z]+", k))
          return str(var)
        else:
          return str("Sorry, I couldn't understand that.")
    except:
        return str("Sorry, I couldn't understand that.")

def query_str(user_input):
    global listing_url
    list_of_empty_params = filter(lambda x:user_session[x]==None, user_session.keys())
    if len(list_of_empty_params) == 4:
        response = wit.text_query(user_input, access_token)
        print 'response --> ', response
        json_res = json.loads(response)
        intent = json_res['outcomes'][0]['intent']
        confidence = json_res['outcomes'][0]['confidence']
        entities = json_res['outcomes'][0]['entities']
        message = ""

        #print  "\n",intent, confidence, entities,"\n\n"
        # if "wikipedia_search_query" in entities:
        #     wikipedia_search_query =  entities['wikipedia_search_query'][0]['value']
        #     wiki_result = wiki_call(wikipedia_search_query)
        #     print wiki_result
        if intent=="seeker":
            global user_session
            if 'search_intent' in entities:
                search_intent = entities['search_intent'][0]['value']
                if search_intent=='rent':
                    user_session['search_intent'] = 'rent'
                elif search_intent in ['sale','purchase']:
                    user_session['search_intent'] = 'sale'
            else:
                user_session['search_intent'] = None

            if 'room_type' in entities:
                room_type = entities['room_type'][0]['value']
                user_session['bed_rooms']  = room_type_parse(room_type)
            else:
                user_session['room_type'] = None

            if 'area' in entities:
                user_session['area'] = entities['area'][0]['value']
            else:
                user_session['area'] = None

            list_of_empty_params = filter(lambda x:user_session[x]==None, user_session.keys())
            #print list_of_empty_params
            while None in user_session.values():
                message = reply_back_now(entity=list_of_empty_params[0])
                break
            
            return message
                # for each in list_of_empty_params:
                #     reply_back_now(entity=each)
                #     user_input = raw_input()
                #     main_parse(user_input, each)
                #     #print user_session
                #     list_of_empty_params = filter(lambda x:user_session[x]==None, user_session.keys())
        elif intent=="greetings":
            name = entities['name'][0]['value']
            user_name = name
            return "Hello " + name + "!! Please tell me your requirement?"
        elif intent=="about":
            return graph_query_str(user_input)
        elif intent=='UNKNOWN':
            return "Sorry, I couldn't understand that. I am still learning."
            # import sys
            # sys.exit(1)
    elif len(list_of_empty_params) == 0:
        response = wit.text_query(user_input, access_token)
        print 'response --> ', response
        json_res = json.loads(response)
        intent = json_res['outcomes'][0]['intent']
        confidence = json_res['outcomes'][0]['confidence']
        entities = json_res['outcomes'][0]['entities']
        message = ""
        if intent=="about":
            return graph_query_str(user_input)
    else:
        entity_to_set = list_of_empty_params[0]
        main_parse(user_input, entity_to_set)
        list_of_empty_params = filter(lambda x:user_session[x]==None, user_session.keys())
        if len(list_of_empty_params)>0:
            return reply_back_now(entity=list_of_empty_params[0])
        else:
            url_formation = "https://www.commonfloor.com/listing-search?city=Bangalore&prop_name[]="+user_session['area']\
            +"&property_location_filter[]="+ user_session['area_code'] +"&use_pp=0&set_pp=1&polygon=1&page=1&page_size=30&\
            search_intent="+user_session['search_intent']+"&min_inr="+user_session['min_inr']+"&max_inr="+\
            user_session['max_inr']+"&house_type[]=Apartment&bed_rooms[]="+str(user_session['bed_rooms'])

            listing_url = url_formation

            page = requests.get(url_formation)
            tree = html.fromstring(page.text)
            message = ""
            t = "".join(tree.xpath("//span[@class='result-count-number']/text()"))

            if int(t)==0:
                message += "Sorry..I didn't find any listing matching your requirements."
            else:
                message += "I could find "+ t +" listings for you."

            message += "Click on the link to have a look at the properties<br /><a href='" + url_formation + "'>Look for it >>>></a><br /> Do you want to look for better project's listing?"
            #message += "Bot finally collects these many values", user_session

            #print "intent = {}\n confidence={}\n entities={}\n wikipedia_search_query={}".format(intent, confidence, entities, wikipedia_search_query)
            #wit.close()
            return message


def graph_query_str(strQuery): 
    result_json = graph_query(strQuery)
    #print result_json
    result_sentences = result_json['result_sentences']
    titles = result_json['titles']
    if len(titles)>0:
        return ' '.join(result_sentences[titles[0][1]])
    else:
        return 'Sorry I didn;t find any result for your query.'

def graph_query(strQuery):
    authenticate("localhost:7474", "neo4j", "maxheap123")
    g = Graph()
    list_of_words = nltk.word_tokenize(strQuery)
    #Tag the words
    pos_tags = nltk.pos_tag(list_of_words)

    print str(pos_tags)
    searchable_tags = []
    current_word = ""
    last_tag = ""
    check_in_attr = []
    for tag in pos_tags:
        if (tag[1][:2] == 'NN'):
            current_word += tag[0].lower() + " "
        elif (tag[1][:2] == 'JJ'):
            if last_tag[:2]!='NN':
                current_word += tag[0].lower() + " "
            else:
                if current_word!="":
                    if current_word[:-1] not in searchable_tags:
                        searchable_tags.append(current_word[:-1])
        #             current_word = ""
        elif (tag[1][:2] == 'WP'):
            check_in_attr.append(tag[0].lower())
        elif (tag[1][:2] == 'VB'):
            searchable_tags.append(tag[0].lower())
            if current_word!="":
                if current_word[:-1] not in searchable_tags:
                    searchable_tags.append(current_word[:-1])
                current_word = ""
        else:
            if current_word!="":
                if current_word[:-1] not in searchable_tags:
                    searchable_tags.append(current_word[:-1])
                current_word = ""
        last_tag = tag[1]

    if current_word!="":
        if current_word[:-1] not in searchable_tags:
            searchable_tags.append(current_word[:-1])
        current_word = ""

    check_in_attr += searchable_tags

    result_sentences = []
    result = {}
    total_nodes_array = []
    titles = []
    title_ratings = {}
    for tag in searchable_tags:
        query_result = g.cypher.execute("MATCH n where n.name='"+ tag +"' return n.name")
        if len(query_result)!=0:
            for record in query_result:
                total_nodes_array.append(str(record[0]))
        else:
            tag_array = tag.split(' ')
            if len(tag_array)>1:
                tagCount = len(tag_array)-1
                #print 'processing tag split', tag, ' and tag count=>', tagCount
                node_exists = False
                while(tagCount>1 and not node_exists):
                    str_segments = str_segment(tag, tagCount)
                    print 'print str_segments => ', str(str_segments)
                    for str_seg in str_segments:
                        for record in g.cypher.execute("MATCH n where n.name='"+ str_seg +"' return n.name"):
                            if record[0] is not None:
                                #print 'here', str(record[0])
                                total_nodes_array.append(str(record[0]))
                                node_exists = True
                    tagCount -= 1

    if len(total_nodes_array)==1:
        print "inside one node **********************"
        getting_answer = False
        for match_attr in check_in_attr:
            for record in g.cypher.execute("MATCH n WHERE n.name = '" + total_nodes_array[0] + "' RETURN n."+match_attr.replace(' ','_')):
                if record[0] is not None:
                    print 'result -> ', record[0]
                    result['no_url'] = [str(record[0]).capitalize()]
                    # create the table (topic, url, rating)
                    titles.append(['', 'no_url', 100])
                    getting_answer = True
                    break


        if not getting_answer:
            for record in g.cypher.execute("MATCH (n)-[r]-() WHERE n.name = '" + total_nodes_array[0] + "' RETURN r.sentence, r.url, r.page_title ORDER BY r.time_created"):
                if record[0] is not None:
                    if record[1] not in result:
                        result[record[1]] = []
                        # create the table (topic, url, rating)
                        titles.append([record[2], record[1], difflib.SequenceMatcher(None,strQuery,record[2]).ratio()*100])
                    if str(record[0]).capitalize() not in result[record[1]]:
                        result[record[1]].append(str(record[0]).capitalize())

            similar_nodes = []
            for record in g.cypher.execute("MATCH (n)-[r]-(n2) WHERE type(r)='equals' and n.name = '" + total_nodes_array[0] + "' RETURN n2.name"):
                similar_nodes.append(str(record[0]))

            for similar_node in similar_nodes:
                for record in g.cypher.execute("MATCH (n)-[r]-() WHERE n.name = '" + similar_node + "' RETURN r.sentence, r.url, r.page_title ORDER BY r.time_created"):
                    if record[0] is not None:
                        if record[1] not in result:
                            result[record[1]] = []
                            # create the table (topic, url, rating)
                            titles.append([record[2], record[1], difflib.SequenceMatcher(None,strQuery,record[2]).ratio()*100])
                        if str(record[0]).capitalize() not in result[record[1]]:
                            result[record[1]].append(str(record[0]).capitalize())
    elif len(total_nodes_array)>1:
        print "inside ", len(total_nodes_array) ," node **********************"
        total_nodes_array.sort()
        i = 0
        for node1 in total_nodes_array:
            i += 1
            for node2 in total_nodes_array[i:]:
                if node1!=node2:
                    similar_node_1 = [node1]
                    for record in g.cypher.execute("MATCH (n)-[r]-(n2) WHERE type(r)='equals' and n.name = '" + node1 + "' RETURN n2.name"):
                        similar_node_1.append(str(record[0]))

                    similar_node_2 = [node2]
                    for record in g.cypher.execute("MATCH (n)-[r]-(n2) WHERE type(r)='equals' and n.name = '" + node2 + "' RETURN n2.name"):
                        similar_node_2.append(str(record[0]))

                    for node_1 in similar_node_1:
                        for node_2 in similar_node_2:
                            for record in g.cypher.execute("MATCH (n1)-[r]-(n2) WHERE n1.name = '" + node_1 + "' and n2.name = '" + node_2 + "' RETURN r.sentence, r.url, r.page_title ORDER BY r.time_created"):
                                if record[0] is not None:
                                    if record[1] not in result:
                                        result[record[1]] = []
                                        # create the table (topic, url, rating)
                                        titles.append([record[2], record[1], difflib.SequenceMatcher(None,strQuery,record[2]).ratio()*100])
                                    if str(record[0]).capitalize() not in result[record[1]]:
                                        result[record[1]].append(str(record[0]).capitalize())

    titles.sort(key=operator.itemgetter(2), reverse=True)
    titles = titles[:5]

    result_json = {}
    result_json['result_sentences'] = result
    result_json['titles'] = titles
    return result_json

def str_segment(sentence, no_of_words):
    values = []
    count = 0
    words = sentence.split(' ')
    while (count+no_of_words)<len(words)+1:
        values.append(' '.join(words[count:count+no_of_words]))
        count += 1

    return values
