#!/usr/bin/env python
#
# Copyright 2009 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

# coding: utf-8

import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.httpclient
import os.path
import uuid
import nltk
from nltk.parse import stanford
import torndb
import json
from pycket.session import SessionMixin
from pycket.notification import NotificationMixin
import urllib
import api_call
import rdf_triple
import time
import adminSettings

from textblob.classifiers import NaiveBayesClassifier
from textblob import TextBlob
from datetime import datetime

from py2neo import authenticate, Graph
from py2neo import Node, Relationship
from py2neo import error
from lxml import html
import requests

import difflib
import math
import operator
import logging
import query


import tornado.escape
from tornado import gen
from tornado.concurrent import Future
from tornado.options import define, options, parse_command_line
from tornado.web import asynchronous

#from bulbs.neo4jserver import Graph, Config, NEO4J_URI

# os.environ['STANFORD_PARSER'] = './jars'
# os.environ['STANFORD_MODELS'] = './jars'

define("port", default=8888, help="run on the given port", type=int)
define("debug", default=False, help="run in debug mode")

#define("host", default="stageaira.commonfloor.com", help="host")
define("host", default="localhost", help="host")
define("database", default="aira", help="database")
define("user", default="cfx_user", help="user")
define("password", default="cfx_user@123", help="password")
define("cookie_secret", default="L8LwECiNRxq2N0N2eGxx9MZlrpmuMEimlydNX/vt1LM=", help="cookie_secret")

requirementList = [
                    ("City", 'city'),
                    ("Location", 'property_location_filter'),
                    ("Search Type", 'search_intent'),
                    ("Room Type", 'bed_rooms'),
                    ("Budget", 'max_inr'),
                    ("House Type", 'house_type'),
                    ]

train = [
            ("Yes please prioritize it", 'prioritizeIntent'),
            ("Show me the first one", 'listingIntent'),
            ("Show me the second one", 'listingIntent'),
            ("Show me the third one", 'listingIntent'),
            ("Show me the fourth one", 'listingIntent'),
            ('Can you show me some pictures', 'picturesIntent'),
            ('Can you show me some pictures of this house', 'picturesIntent'),
            ('Can you show the pictures again','picturesIntent'),
            ('Can you show the pictures of the house again','picturesIntent'),
            ('Give me the tour of this locality','tourIntent'),
            ('I like this house','likeHouseIntent'),
            ('Sure Please call the owner','callOwnerIntent')
        ]

cl = NaiveBayesClassifier(train)
session_id = uuid.uuid4()

builder_feature_set = "'architecture|construction|slab|water|electricity|security|amenities|swimming pool|gym|pavement|walk|open area|greenery|intercom|wood work|interior'"
builder_feature_set_array = ['architecture','construction','slab','water','electricity','security','amenities','swimming pool','gym','pavement','walk','open area','greenery','intercom','wood work','interior']
builder_recogniser_set = "'developer|group|Developer|Group|estates|Estates|project|Projects'"
builder_recogniser_set_array = ['developer','group','Developer','Group','estates','Estates','project','Projects']

static_path=os.path.join(os.path.dirname(__file__), "static/")

class DBHandler(tornado.web.RequestHandler):
    def get(self):
        db = torndb.Connection(
            host=options.host, database=options.database,
            user=options.user, password=options.password)

        rows = db.query("select offer_id, broker_id from group_deal_offers")
        db.close()

        top = "<html><body><b>Posts</b><br /><br />"
        table = "<table border=\"1\"><col width=\"50\" /><col width=\"200\" />"
        for row in rows:
            table += "<tr><td>" + str(row["offer_id"]) + "</td><td>" + str(row["broker_id"]) + "</td></tr>"
        bottom = "</body></html>"
        self.write(top+table+bottom)

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        # print "before this"
        self.write("Hello, world from Aira")
        # import pyttsx
        # engine = pyttsx.init()
        # engine.say("Hello I am aira")
        # print "till here"
        # engine.runAndWait()
        # print "after this"

class SummarizationHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("summarization.html", messages = None)

    def post(self):
        feature_set_posts = {}
        project_set_posts = {}
        developer_sentences = []
        searchEntity = self.get_argument('searchEntity', 'No data received')

        # builder_feature_set_str = ""
        # for builder_feature in builder_feature_set:
        #     builder_feature_set_str += "INSTR(post_body,'" + builder_feature + "')>0 or "

        # builder_feature_set_str = builder_feature_set_str[:-4]

        # print builder_feature_set_str

        db = torndb.Connection(options.host, options.database, options.user, options.password)
        
        #strQuery = "select post_id, post_body from forum_post where post_body like %s and post_body REGEXP %s"
        #print strQuery
        #rows = db.query(strQuery, "%" + searchEntity + "%", builder_feature_set)

        strQuery = "select post_id, reply_body as post_body from forum_reply where reply_body like %s and reply_body REGEXP %s and reply_body REGEXP %s"
        #print strQuery
        rows = db.query(strQuery, "%" + searchEntity + "%",builder_recogniser_set,builder_feature_set)

        #rows = rows + rows1

        db.close()

        #print rows
        sent_tokenize = nltk.data.load('tokenizers/punkt/english.pickle')
        if rows:
            top = "<html><body><b>Posts</b><br /><br />"
            table = "<table border=\"1\"><col width=\"20\" /><col width=\"50\" /><col width=\"400\" /><col width=\"400\" />"
        
            counter = 1
            for row in rows:
                developer_info_only = -1
                testimonial = TextBlob(row['post_body'])
                polarity = testimonial.sentiment.polarity
                for feature_set in builder_feature_set_array:
                    if feature_set in row['post_body']:
                        #print "feature_set -> ", feature_set
                        if feature_set in feature_set_posts:
                            feature_post = {}
                            feature_post['post'] = row['post_body']
                            feature_post['polarity'] = polarity
                            if row['post_body'] not in feature_set_posts[feature_set]:
                                feature_set_posts[feature_set].append(feature_post)
                        else:
                            feature_post = {}
                            feature_post['post'] = row['post_body']
                            feature_post['polarity'] = polarity
                            feature_set_posts[feature_set] = [feature_post]

                        #self.write(str(feature_set_posts) + "<br /><br />")



                #print "row['post_body'] -> ", row['post_body']
                #print feature_set_posts['amenities']
                #self.write("*******************")
                #for post in feature_set_posts['amenities']:
                #    self.write(post + "<br /><br />")

                #self.write(feature_top+feature_table+feature_bottom)
                sentences = sent_tokenize.tokenize(row['post_body'])
                sent_pos_tags = ""
                for sentence in sentences:
                    list_of_words = nltk.word_tokenize(sentence)
                    #Tag the words
                    pos_tags = nltk.pos_tag(list_of_words)

                    useful_words = []
                    current_word = ""
                    
                    for tag in pos_tags:
                        if tag[0].startswith(searchEntity):
                            current_word = tag[0] + " "
                        else:
                            if current_word != "":
                                if(tag[1].startswith('NN')):
                                    if tag[0] not in builder_recogniser_set_array:
                                        current_word += tag[0] + " "
                                        developer_info_only = 0
                                    else:
                                        if developer_info_only == -1:
                                            developer_info_only = 1
                                        current_word = ""
                                else:
                                    full_words = current_word.split( )
                                    if len(full_words)>1:
                                        useful_words.append(current_word[:-1])
                                        current_word = ""
                                    else:
                                        current_word = ""

                    # if current_word!="":
                    #     useful_words.append(current_word[:-1]) 

                    #print "useful_words => ", str(useful_words)

                    for word in useful_words:
                        #print "word => ", word, " => ", row['post_body']
                        is_recogniseer_exist = False
                        if searchEntity in word:
                            for recogniser in builder_recogniser_set_array:
                                if recogniser in word:
                                    is_recogniseer_exist = True

                        if not is_recogniseer_exist:
                            if word in project_set_posts:
                                recogniser_post = {}
                                recogniser_post['post'] = row['post_body']
                                recogniser_post['polarity'] = polarity
                                if recogniser_post not in project_set_posts[word]:
                                    project_set_posts[word].append(recogniser_post)
                            else:
                                recogniser_post = {}
                                recogniser_post['post'] = row['post_body']
                                recogniser_post['polarity'] = polarity
                                project_set_posts[word] = [recogniser_post]

                    sent_pos_tags += str(useful_words) + "<br /><br />"

                table += "<tr><td>" + str(counter) + "</td><td>" + row['post_id'] + "</td><td>" + row['post_body'] + "</td><td>" + str(sent_pos_tags) + "</td></tr>"
                counter += 1
                if developer_info_only == 1:
                    developer_sentences.append(row['post_body'])
            bottom = "</body></html>"

            feature_top = "<html><body><h1>Posts</h1><br /><br />"
            feature_table = "<table border=\"1\"><col width=\"50\" /><col width=\"200\" />"

            for feature_set_post in feature_set_posts:
                post_data = ""
                polarity_data = ""
                avg_polarity = 0.0
                count_number = 0
                for feature_post in feature_set_posts[feature_set_post]:
                    if feature_post['polarity']<0:
                        post_data += "<font color='red'>" + feature_post['post'] + "</font><br /><br />"
                    else:
                        post_data += "<font color='green'>" + feature_post['post'] + "</font><br /><br />"
                    polarity_data += str(feature_post['polarity']) + "<br /><br />"
                    avg_polarity += feature_post['polarity']
                    count_number += 1

                avg_polarity = avg_polarity/count_number

                feature_table += "<tr><td>" + feature_set_post + "</td><td>" + post_data + "</td></tr>"
            
            feature_table += "</table>"
            feature_bottom = "</body></html>"
            #self.write(feature_top+feature_table+feature_bottom)

            recogniser_top = "<html><body><div align=\"center\"><h1>" + searchEntity + " Posts</h1></div>"
            recogniser_table = "<table border=\"1\"><col width=\"50\" /><col width=\"400\" />"


            #self.write(str(project_set_posts))
            for project_set_post in project_set_posts:
                post_data = ""
                polarity_data = ""
                avg_polarity = 0.0
                count_number = 0
                for recogniser_post in project_set_posts[project_set_post]:
                    if feature_post['polarity']<0:
                        post_data += "<font color='red'>" + recogniser_post['post'] + "</font><br /><br />"
                    else:
                        post_data += "<font color='green'>" + recogniser_post['post'] + "</font><br /><br />"
                    polarity_data += str(recogniser_post['polarity']) + "<br /><br />"
                    avg_polarity += recogniser_post['polarity']
                    count_number += 1

                avg_polarity = avg_polarity/count_number

                recogniser_table += "<tr><td>" + project_set_post + "</td><td>" + post_data + "</td></tr>"
            
            recogniser_table += "</table>"
            recogniser_bottom = "</body></html>"
            
            developer_html = "<ol>"
            for developer_sentence in developer_sentences:
                developer_html += "<li>" + developer_sentence + "</li><br />"
            developer_html += "</ol>"
            #self.write(str(developer_html))

            self.write(recogniser_top+ str(developer_html) + "<table><col width=\"450\" /><col width=\"450\" /><tr valign=\"top\"><td>" +feature_table+ "</td><td style=\"width:450px\">" + recogniser_table + "</td></tr></table>" +recogniser_bottom)

            #self.write(top+table+bottom)

        #self.write(searchEntity)

class PicturesHandler(tornado.web.RequestHandler):
    def get(self):
        global pic_urls
        self.render("index.html", data_urls = pic_urls)

class StartHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("start.html", static_path = static_path)

class ChatBoxHandler(tornado.web.RequestHandler):
    def get(self):
        global global_message_buffer
        global_message_buffer = MessageBuffer()
        self.render("chatbox.html", messages=global_message_buffer.cache)

class UnstructuredDataHandler(tornado.web.RequestHandler):
    def strip_non_ascii(self, string):
        ''' Returns the string without non ASCII characters'''
        stripped = (c for c in string if 0 < ord(c) < 127)
        return ''.join(stripped)

    def get(self):
        global new_nodes_from_url
        global existing_nodes_from_url
        global relations

        new_nodes_from_url = []
        existing_nodes_from_url = []
        relations = []

        self.render("feature_set.html", static_path = static_path, new_nodes_from_url= None, existing_nodes_from_url= None,relations= None)
    def post(self):
        global new_nodes_from_url
        global existing_nodes_from_url
        global provided_url
        global relations

        authenticate("localhost:7474", "neo4j", "maxheap123")
        g = Graph()
        try:
            g.schema.create_uniqueness_constraint("Subject", "name")
        except:
            pass

        print self.request.arguments
        if 'url' in self.request.arguments:
            url = self.get_argument('url')
            provided_url = url
            page = requests.get(url)
            tree = html.fromstring(page.text)
            t = tree.xpath("//div[@class='fulldetal_content hyphenate']//p")
            t_questions = tree.xpath("//div[@class='fulldetal_content hyphenate']//p//strong")

            whole_text = ""
            for elem in t:
                for txt in elem.xpath('text()'):
                    whole_text += str(self.strip_non_ascii(txt).lower().encode('utf-8')) + " "

            for elem in t_questions:
                for txt in elem.xpath('text()'):
                    #print "******************",txt
                    whole_text += str(self.strip_non_ascii(txt).lower().encode('utf-8')) + " "

            tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
            sentences = tokenizer.tokenize(whole_text)
            
            nodes_from_url = []
            new_nodes_from_url = []
            existing_nodes_from_url = []
            relations = []

            for sentence in sentences:
                list_of_words = nltk.word_tokenize(sentence)
                pos_tags = nltk.pos_tag(list_of_words)

                current_word = ""
                last_tag = ""
                for tag in pos_tags:
                    if (tag[1][:2] == 'NN'):
                        current_word += tag[0].lower() + " "
                    elif (tag[1][:2] == 'JJ'):
                        if last_tag[:2]!='NN':
                            current_word += tag[0].lower() + " "
                        else:
                            if current_word!="":
                                if current_word[:-1] not in nodes_from_url:
                                    nodes_from_url.append(current_word[:-1])
                                current_word = ""
                    else:
                        if current_word!="":
                            if current_word[:-1] not in nodes_from_url:
                                nodes_from_url.append(current_word[:-1])
                            current_word = ""
                    last_tag = tag[1]

                if current_word!="":
                    if current_word[:-1] not in nodes_from_url:
                        nodes_from_url.append(current_word[:-1])
                    current_word = ""

            for record in g.cypher.execute("MATCH n where n.name IN ['" + '\',\''.join(nodes_from_url) + "'] return n.name"):
                existing_nodes_from_url.append(str(record[0]))

            new_nodes_from_url = [item for item in nodes_from_url if item not in existing_nodes_from_url]

            for record in g.cypher.execute("MATCH (n)-[r]->(n2) WHERE type(r)=~ 'equals' or type(r)=~ 'not_equals' RETURN n.name as first_node,type(r) as relation,n2.name as second_node"):
                print record
                relations.append(record)

            self.render("feature_set.html", static_path = static_path, new_nodes_from_url= new_nodes_from_url, existing_nodes_from_url= existing_nodes_from_url, relations= relations)
        elif 'select_first_node' in self.request.arguments:
            if new_nodes_from_url:
                first_node = self.get_argument('select_first_node')
                second_node = self.get_argument('select_second_node')
                similarity_value = self.get_argument('select_similarity')
                similarity = "equals"
                if similarity_value=='!=':
                    similarity = "not_equals"
                strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ similarity +"]->(b) RETURN r"
                for record in g.cypher.execute(strQuery):
                    print(record)

                relations = []
                for record in g.cypher.execute("MATCH (n)-[r]->(n2) WHERE type(r)=~ 'equals' or type(r)=~ 'not_equals' RETURN n.name as first_node,type(r) as relation,n2.name as second_node"):
                    relations.append(record)

                self.render("feature_set.html", static_path = static_path, new_nodes_from_url= new_nodes_from_url, existing_nodes_from_url= existing_nodes_from_url, relations= relations)
        else:
            if 'selected_nodes' in self.request.arguments:
                if new_nodes_from_url:
                    selected_nodes = self.get_arguments('selected_nodes')
                    print 'selected_nodes -> ', selected_nodes
                    for selected_node in selected_nodes:
                        print 'selected_node -> ', selected_node
                        node = Node("Subject", name=selected_node)
                        try:
                            g.create(node)
                        except Exception as e:
                            print e
                            pass

                    new_nodes_from_url = [item for item in new_nodes_from_url if item not in selected_nodes]
                    existing_nodes_from_url.extend(selected_nodes)

            self.render("feature_set.html", static_path = static_path, new_nodes_from_url= new_nodes_from_url, existing_nodes_from_url= existing_nodes_from_url, relations= relations)


class AnswerHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("query.html", result_sentences = None, static_path = static_path)

    def post(self):
        print self.request.arguments
        strQuery = self.get_argument('searchEntity', 'No data received')
        print strQuery
        authenticate("localhost:7474", "neo4j", "maxheap123")
        g = Graph()
        list_of_words = nltk.word_tokenize(strQuery)
        #Tag the words
        pos_tags = nltk.pos_tag(list_of_words)

        print str(pos_tags)
        searchable_tags = []
        current_word = ""
        last_tag = ""
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

        # for tag in pos_tags:
        #     if tag[1][:2] == 'NN':
        #         searchable_tags.append(tag[0].lower())

        result_sentences = []
        total_nodes_array = []
        for record in g.cypher.execute("MATCH n where n.name IN ['" + '\',\''.join(searchable_tags) + "'] return n.name"):
            total_nodes_array.append(str(record[0]))

        if len(total_nodes_array)==1:
            print "inside one node **********************"
            for record in g.cypher.execute("MATCH (n)-[r]-() WHERE n.name = '" + total_nodes_array[0] + "' RETURN r.sentence ORDER BY r.time_created"):
                if str(record[0]).capitalize() not in result_sentences and record[0] is not None:
                    result_sentences.append(str(record[0]).capitalize())

            similar_nodes = []
            for record in g.cypher.execute("MATCH (n)-[r]-(n2) WHERE type(r)='equals' and n.name = '" + total_nodes_array[0] + "' RETURN n2.name"):
                similar_nodes.append(str(record[0]))

            for similar_node in similar_nodes:
                for record in g.cypher.execute("MATCH (n)-[r]-() WHERE n.name = '" + similar_node + "' RETURN r.sentence ORDER BY r.time_created"):
                    if str(record[0]).capitalize() not in result_sentences and record[0] is not None:
                        result_sentences.append(str(record[0]).capitalize())
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
                                for record in g.cypher.execute("MATCH (n1)-[r]->(n2) WHERE n1.name = '" + node_1 + "' and n2.name = '" + node_2 + "' RETURN r.sentence ORDER BY r.time_created"):
                                    if str(record[0]).capitalize() not in result_sentences and record[0] is not None:
                                        result_sentences.append(str(record[0]).capitalize())



        # result_sentences = []
        # for search_tag in searchable_tags:
        #     # similar_nodes = [search_tag]
        #     # for record in g.cypher.execute("MATCH (n)-[r]-(n2) WHERE type(r)='equals' and n.name = '" + search_tag + "' RETURN n2.name"):
        #     #     similar_nodes.append(str(record[0]))

        #     for similar_node in similar_nodes:
        #         for record in g.cypher.execute("MATCH (n)-[r]->() WHERE n.name = '" + similar_node + "' RETURN r.sentence ORDER BY r.time_created"):
        #             if str(record[0]) not in result_sentences and record[0] is not None:
        #                 result_sentences.append(str(record[0]))

        #         for record in g.cypher.execute("MATCH (n)-[r]->() WHERE type(r)=~ '.*"+ similar_node +".*' RETURN r.sentence ORDER BY r.time_created"):
        #             if str(record[0]) not in result_sentences and record[0] is not None:
        #                 result_sentences.append(str(record[0]))

        self.render("query.html", result_sentences = result_sentences, static_path = static_path)
        #self.write(str(searchable_tags))

class StrcutureAnswerHandler(tornado.web.RequestHandler):
    # And if you want a list of strings:
    def str_segment(self,sentence, no_of_words):
        values = []
        count = 0
        words = sentence.split(' ')
        while (count+no_of_words)<len(words)+1:
            values.append(' '.join(words[count:count+no_of_words]))
            count += 1

        return values

    def get(self):
        self.render("query.html", result_sentences = None, query=None, titles=None, title_ratings=None, static_path = static_path)

    def post(self):
        print self.request.arguments
        strQuery = self.get_argument('searchEntity', 'No data received')
        print strQuery
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
        # for tag in pos_tags:
        #     if tag[1][:2] == 'NN':
        #         searchable_tags.append(tag[0].lower())

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
                        str_segments = self.str_segment(tag, tagCount)
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



        # result_sentences = []
        # for search_tag in searchable_tags:
        #     # similar_nodes = [search_tag]
        #     # for record in g.cypher.execute("MATCH (n)-[r]-(n2) WHERE type(r)='equals' and n.name = '" + search_tag + "' RETURN n2.name"):
        #     #     similar_nodes.append(str(record[0]))

        #     for similar_node in similar_nodes:
        #         for record in g.cypher.execute("MATCH (n)-[r]->() WHERE n.name = '" + similar_node + "' RETURN r.sentence ORDER BY r.time_created"):
        #             if str(record[0]) not in result_sentences and record[0] is not None:
        #                 result_sentences.append(str(record[0]))

        #         for record in g.cypher.execute("MATCH (n)-[r]->() WHERE type(r)=~ '.*"+ similar_node +".*' RETURN r.sentence ORDER BY r.time_created"):
        #             if str(record[0]) not in result_sentences and record[0] is not None:
        #                 result_sentences.append(str(record[0]))

        #print result
        # refined_result = str(result)
        # for tag in searchable_tags:
        #     refined_result.replace(tag, "<b>"+tag+"</b>")

        titles.sort(key=operator.itemgetter(2), reverse=True)
        titles = titles[:5]


        # print the table
        #print(titles)

        #print titles.sort(key=lambda x: x['rating'])
        #print sorted(titles,key=itemgetter('rating'))
        self.render("query.html", result_sentences = result, query = strQuery, titles=titles, static_path = static_path)

class CreateRelationshipHandler(tornado.web.RequestHandler):
    def add_relations(self, line, first_node, second_node, negative_line):
        global predicate_word_for_a_line
        print 'in add relation line => ', line , ', first_node => ', first_node, ' second_node => ', second_node
        authenticate("localhost:7474", "neo4j", "maxheap123")
        g = Graph()
        first_index = line.index(first_node)
        second_index = line.index(second_node)
        used_line = line[first_index+len(first_node):second_index]
        verbs = []
        list_of_words = nltk.word_tokenize(used_line)
        pos_tags = nltk.pos_tag(list_of_words)
        verb_word = ""
        for tag in pos_tags:
            if tag[1][:2] == 'VB':
                verb_word += tag[0].lower() + "_"
            else:
                if verb_word!="":
                    verbs.append(verb_word[:-1])
                    verb_word = ""

        if verb_word!="":
            verbs.append(verb_word[:-1])
            
        print 'in add relation verbs ---------------------> ', str(verbs)
        # if negative_line:
        #     self.write("Negative sentence is => " + line)

        verb_len = len(verbs)
        if verb_len!=0:
            verb = '_'.join(verbs)
            #for verb in verbs:
            self.write("<b>Relationship added => </b> (" + first_node + ") => (" + verb + ") => (" + second_node+ ")<br />")
            strQuery = ""
            if negative_line==True:
                strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ verb +"{sentence:'" + line + "',neg:True,time_created:'" + str(time.time()) + "'}]->(b) RETURN r"
            else:
                strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ verb +"{sentence:'" + line + "',time_created:'" + str(time.time()) + "'}]->(b) RETURN r"
            for record in g.cypher.execute(strQuery):
                print(record)
        else:
            if predicate_word_for_a_line == "":
                print "********************************"
                rdf = rdf_triple.RDF_Triple(line)
                predicate_word_for_a_line = rdf.get_predicate_word()
                print "********************************"
            if predicate_word_for_a_line != "":
                strQuery = ""
                self.write("<b>Relationship added => </b> (" + first_node + ") => (" + predicate_word_for_a_line + ") => (" + second_node+ ")<br />")
                if negative_line==True:
                    strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ predicate_word_for_a_line +"{sentence:'" + line + "',neg:True,time_created:'" + str(time.time()) + "'}]->(b) RETURN r"
                else:
                    strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ predicate_word_for_a_line +"{sentence:'" + line + "',time_created:'" + str(time.time()) + "'}]->(b) RETURN r"
                for record in g.cypher.execute(strQuery):
                    print(record)


    def strip_non_ascii(self, string):
        ''' Returns the string without non ASCII characters'''
        stripped = (c for c in string if 0 < ord(c) < 127)
        return ''.join(stripped)

    def post(self):
        global predicate_word_for_a_line
        #global provided_url
        authenticate("localhost:7474", "neo4j", "maxheap123")
        g = Graph()
        url=self.get_argument('url', 'No data received')

        #url = "https://www.commonfloor.com/guide/partial-occupancy-certificate-know-it-all-53465.html"
        
        from lxml import html
        import requests
        page = requests.get(url)
        tree = html.fromstring(page.text)
        #t = tree.xpath("//p[@style='text-align: justify;']")
        t = tree.xpath("//div[@class='fulldetal_content hyphenate']//p")
        t1 = tree.xpath("//div[@class='fulldetal_content hyphenate']//p//span")

        whole_text = ""
        for elem in t:
            for txt in elem.xpath('text()'):
                whole_text += str(self.strip_non_ascii(txt).lower().encode('utf-8')) + " "

        for elem in t1:
            for txt in elem.xpath('text()'):
                whole_text += str(self.strip_non_ascii(txt).lower().encode('utf-8')) + " "

        print whole_text

        tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
        sentences = tokenizer.tokenize(whole_text)

        existing_nodes = []
        for record in g.cypher.execute("MATCH n RETURN n.name"):
            existing_nodes.append(record[0])

        print str(existing_nodes)

        counter = 0
        for line in sentences:
            predicate_word_for_a_line = ""
            counter += 1
            print "(", counter ,")", line
            if line:
                list_of_words = nltk.word_tokenize(line)
                pos_tags = nltk.pos_tag(list_of_words)


                testimonial = TextBlob(line)
                polarity = testimonial.sentiment.polarity
                negative_line = False
                if polarity<0:
                    negative_line = True

                intersection_words = []
                for node in existing_nodes:
                    if node in line:
                        intersection_words.append(node)

                print 'before intersection_words filtering -> ', intersection_words
                filtered_interesection_words = list(intersection_words)
                for intersection_word_1 in intersection_words:
                    for intersection_word_2 in intersection_words:
                        if (intersection_word_1!=intersection_word_2):
                            # if ' ' not in intersection_word_1:
                            #     if (intersection_word_1 in list(intersection_word_2.split( ))):
                            #         if intersection_word_1 in filtered_interesection_words:
                            #             filtered_interesection_words.remove(intersection_word_1)
                            # else:
                            if (intersection_word_1 in intersection_word_2):
                                if intersection_word_1 in filtered_interesection_words:
                                    filtered_interesection_words.remove(intersection_word_1)

                print 'after intersection_words filtering -> ', filtered_interesection_words
                #interesection_words = list(filtered_interesection_words)

                len_words = len(filtered_interesection_words)
                if len_words>1:
                    print 'verb'
                    for first_node in filtered_interesection_words:
                        for second_node in filtered_interesection_words:
                            if line.index(first_node)<line.index(second_node):
                                self.add_relations(line, first_node, second_node, negative_line)
                    #find verb
                elif len_words==1:
                    first_node = filtered_interesection_words[0]
                    subject = ""
                    for tag in pos_tags:
                        if tag[1][:2] == 'NN' and (tag[0] not in first_node):
                            subject = tag[0]
                            break

                    if subject!="":
                        subjectNode = Node("Subject", name=subject)
                        try:
                            g.create(subjectNode)
                            self.write("<b>Node created</b> -> " + subject + "<br />")
                        except Exception as e:
                            print e
                            pass

                        if line.index(first_node)<line.index(subject):
                            self.add_relations(line, first_node, subject, negative_line)
                        else:
                            self.add_relations(line, subject, first_node, negative_line)

                        print 'noun' and 'verb'
                        #find one more noun
                    else:
                        #self.write('unmatched sentence is -> ' + line + '<br />')
                        print 'unmatched sentence is -> ', line
                else:
                    #self.write('unmatched sentence is -> ' + line + '<br />')
                    print 'unmatched sentence is -> ', line

                print 'intersection_words -> ', len(filtered_interesection_words)
                # print 'verbs -> ', str(verbs)
                # print 'verbs_pos -> ', str(verbs_pos)

        #self.write(str(sentences))

class ParseHandler(tornado.web.RequestHandler):
    def strip_non_ascii(self, string):
        ''' Returns the string without non ASCII characters'''
        stripped = (c for c in string if 0 < ord(c) < 127)
        return ''.join(stripped)

    def get(self):
        authenticate("localhost:7474", "neo4j", "maxheap123")
        g = Graph()
        print g
        try:
            g.schema.create_uniqueness_constraint("Subject", "name")
        except:
            pass

        #url='https://www.commonfloor.com/guide/partial-occupancy-certificate-know-it-all-53465.html'
        url = 'www.google.com'

        from lxml import html
        import requests
        page = requests.get(url)
        tree = html.fromstring(page.text)
        t = tree.xpath("//p[@style='text-align: justify;']")

        whole_text = ""

        #counter = 0

        for elem in t:
            for txt in elem.xpath('text()'):
                #if counter>5:
                whole_text += str(self.strip_non_ascii(txt).lower().encode('utf-8')) + " "
                #counter += 1

        #print whole_text

        tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
        sentences = tokenizer.tokenize(whole_text)

        for record in g.cypher.execute("MATCH (a:Subject) OPTIONAL MATCH (a)-[r1]-() DELETE a,r1"):
            print(record)

        # parser = stanford.StanfordParser(model_path="./jars/stanford-parser-3.5.2-models/edu/stanford/nlp/models/lexparser/englishPCFG.ser.gz")
        # sentences = parser.parse(whole_text.encode('utf-8'))
        #print sentences
        counter = 0
        for line in sentences:
            counter += 1
            print "(", counter ,")", line
            if line:
                if "\xe2" in line:
                    print repr(line.replace("\xe2",""))
                rdf = rdf_triple.RDF_Triple(line)
                rdf.main()
                ans =  rdf.answer
                print ans

                if rdf.subject.word!="" and rdf.predicate.word!="" and rdf.Object.word!="":
                    subjectNode = Node("Subject", name=rdf.subject.word, attributes=json.dumps(rdf.subject.attr))
                    objectNode = Node("Subject", name=rdf.Object.word, attributes=json.dumps(rdf.Object.attr))
                    predicateWord = rdf.predicate.word.replace('-','')
                    strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + rdf.subject.word + "' AND b.name = '" + rdf.Object.word + "' CREATE (a)-[r:"+ predicateWord +"{sentence:'" + rdf.sentence + "',attributes:'" + json.dumps(rdf.predicate.attr) + "',time_created:'" + str(time.time()) + "'}]->(b) RETURN r"


                    try:
                        g.create(subjectNode)
                    except:
                        pass

                    try:
                        g.create(objectNode)
                    except:
                        pass

                    for record in g.cypher.execute(strQuery):
                        print(record)

            # for record in g.cypher.execute("MATCH (a:Subject) OPTIONAL MATCH (a)-[r1]-() DELETE a,r1"):
            #    print(record)

            # for record in g.cypher.execute("MATCH n RETURN n"):
            #     print(record)
        
        #result = tree.xpath("//*[contains(concat(' ', normalize-space(@data-tracking-id), ' '), '2042')]/@href")
        
        # for record in g.cypher.execute("MATCH (d:Person) WHERE d.name =~ '.*Tom.*' RETURN d"):
        #     print(record)
        # for record in g.cypher.execute("MATCH n RETURN n"):
        #     print(record)
        # for record in g.cypher.execute("MATCH (a:Subject) OPTIONAL MATCH (a)-[r1]-() DELETE a,r1"):
        #    print(record)

        # sentence = "A rare black squirrel has become a regular visitor to a suburban garden"
        # rdf = rdf_triple.RDF_Triple(sentence)
        # rdf.main()
        # ans =  rdf.answer
        # print ans

        # subjectNode = Node("Subject", name=rdf.subject.word, attributes=json.dumps(rdf.subject.attr))
        # objectNode = Node("Subject", name=rdf.Object.word, attributes=json.dumps(rdf.Object.attr))
        # strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + rdf.subject.word + "' AND b.name = '" + rdf.Object.word + "' CREATE (a)-[r:"+ rdf.predicate.word +"{sentence:'" + rdf.sentence + "',attributes:'" + json.dumps(rdf.predicate.attr) + "'}]->(b) RETURN r"


        # try:
        #     g.create(subjectNode)
        # except:
        #     pass

        # try:
        #     g.create(objectNode)
        # except:
        #     pass

        # for record in g.cypher.execute(strQuery):
        #     print(record)

        # for record in g.cypher.execute("MATCH (a:Subject) OPTIONAL MATCH (a)-[r1]-() DELETE a,r1"):
        #    print(record)

        for record in g.cypher.execute("MATCH n RETURN n"):
            print(record)


        # parser = stanford.StanfordParser(model_path="./jars/stanford-parser-3.5.2-models/edu/stanford/nlp/models/lexparser/englishPCFG.ser.gz")
        # sentences = parser.parse(("the quick brown fox jumps over the lazy dog", "the quick grey wolf jumps over the lazy fox"))
        # print sentences
        # for line in sentences:
        #     for sentence in line:
        #         print sentence
        self.write(str(sentences))

class NewURLHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("http://www.google.com")
        #self.render("url.html", messages=None)

class BaseHandler(tornado.web.RequestHandler, SessionMixin, NotificationMixin):
    def __init__(self, application, request, **kwargs):
        super(BaseHandler, self).__init__(application, request, **kwargs)

class HelloHandler(BaseHandler):
    def get(self):
        response = {}
        response['speechText'] = "Hello I am Aai ra. Please tell me you requirement"

        for key in self.session.iterkeys():
            print key

        #print "-----------", uuid.uuid4()

        #delete session entry from db - this needs to be removed
        db = torndb.Connection(options.host, options.database, options.user, options.password)
        strQuery = "delete from session_tags"
        db.execute(strQuery)
        db.close()
        #end delete

        #self.session['session_id'] = "1"
        #print self.session
        #print "**********",self.session.get('session_id')
        self.write(response)

class GetIntentHandler(BaseHandler):
    def get(self):
        global last_url
        response = {}
        sentence = urllib.unquote(self.get_argument('sentence')).decode('utf8')
        sentence_pos_tone = True
        if 'remove' in sentence or 'exclude' in sentence:
            sentence_pos_tone = False
        #print text2int("2 BHK")
        #sentence = "I am looking for two BHK house in Koramangala"
        
        #Tokenise the sentence
        list_of_words = nltk.word_tokenize(sentence)
        #Tag the words
        pos_tags = nltk.pos_tag(list_of_words)

        #Collect useful words
        print str(pos_tags)
        current_word = ""
        useful_words = []
        last_tag = ""
        for tag in pos_tags:
            if(tag[1] != 'CD' and last_tag == 'CD'):
                number = text2int(current_word[:-1])
                if number:
                    current_word = number + " "
                if tag[0] == 'square':
                    if current_word and current_word != "":
                        useful_words.append(current_word.strip().lower())
                    current_word = ""
            if(tag[1] == 'CD'):
                if(last_tag != 'CD'):
                    if current_word and current_word != "":
                        useful_words.append(current_word.strip().lower())
                    current_word = tag[0] + " "
                else:
                    current_word = current_word + tag[0] + " "
            elif tag[1]=='IN' and tag[0].lower()=='within':
                current_word = current_word + tag[0] + " "
                if current_word and current_word != "":
                    useful_words.append(current_word.strip().lower())
                current_word = ""
            elif(tag[1].startswith('JJ')):
                current_word = current_word + tag[0] + " "
            elif(tag[1].startswith('NN')):
                current_word = current_word + tag[0] + " "
            else:
                if current_word and current_word != "":
                    useful_words.append(current_word.strip().lower())
                current_word = ""
            last_tag = tag[1]
        
        if current_word and current_word != "":
            useful_words.append(current_word.strip().lower())

        tag_texts = "";

        print useful_words
        #self.write(str(useful_words))

        if(len(useful_words)):
            for useful_word in useful_words:
                tag_texts = tag_texts + "'" + useful_word + "',"

            tag_texts = tag_texts[:-1]

            #Search for these words in dictionary and get json back
            db = torndb.Connection(options.host, options.database, options.user, options.password)
            strQuery = "select tag_text, tag_json from training_tags where tag_text in (" + tag_texts + ")"
            rows = db.query(strQuery)
            db.close()

            #print rows
            if rows:
                #session_id = self.session.get('session_id')
                #if not session_id:
                #    print "************* Session id is missing ************"
                jsonURL = requirementIntent(rows, str(session_id), useful_words, sentence_pos_tone)
                response['url'] = jsonURL['url']
                nextQuery = jsonURL['nextQuery']
                if nextQuery:
                    if '(' in nextQuery:
                        smallNextQuery = nextQuery[:nextQuery.index('(')]
                    else:
                        smallNextQuery = nextQuery
                    response['speechText'] = "Please select any of the given options... Also Would you like to provide " + nextQuery + "."
                    #"Please let me know your " + smallNextQuery
                else:
                    response['speechText'] = "Please select any of the given options."
            else:
                response = restIntent(sentence, pos_tags)
        else:
            response = restIntent(sentence, pos_tags)

        #print response
        #print cl.classify("Can you call the owner")
        if response and 'url' in response:
            last_url = response['url']
        #print "last_url -> ", last_url 
        self.write(response)
        #self.render("url.html", messages=None)

def checkNextQuery(doneParamList):
    if 'city' not in doneParamList:
        return 'City'
    elif 'property_location_filter' not in doneParamList:
        return 'Location'
    elif 'search_intent' not in doneParamList:
        return 'Search Type (like rent or buy)'
    elif 'bed_rooms' not in doneParamList:
        return 'Room Type (like 2 BHK or 3 BHK)'
    elif 'max_inr' not in doneParamList and 'min_inr' not in doneParamList:
        return 'Budget'
    elif 'house_type' not in doneParamList:
        return 'House Type (like Apartment or Villa)'
    else:
        return None



def requirementIntent(rows, session_id, useful_words, sentence_pos_tone):
    global last_intent
    db = torndb.Connection(options.host, options.database, options.user, options.password)
    valueToBeFill = []
    for row in rows:
        if 'maximum budget' in row['tag_text'] or 'max budget' in row['tag_text']  or 'within' in row['tag_text']:
            print 'maximum budget'
            for word in useful_words:
                intValue = text2int(word)
                print intValue
                if intValue:
                    valueToBeFill.append(intValue)
            if len(valueToBeFill)!=0:
                row['tag_json'] = row['tag_json'].replace("to_be_fill", str(max(valueToBeFill)))
        elif 'minimum budget' in row['tag_text'] or 'min budget' in row['tag_text']:
            print 'minimum budget'
            for word in useful_words:
                intValue = text2int(word)
                print intValue
                if intValue:
                    valueToBeFill.append(intValue)
            if len(valueToBeFill)!=0:
                row['tag_json'] = row['tag_json'].replace("to_be_fill", str(min(valueToBeFill)))
        elif 'budget' in row['tag_text']:
            print 'budget'
            for word in useful_words:
                intValue = text2int(word)
                print intValue
                if intValue:
                    valueToBeFill.append(intValue)
            if len(valueToBeFill)==1:
                row['tag_json'] = row['tag_json'].replace("to_be_fill_max", str(max(valueToBeFill))).replace("to_be_fill_min", str(0))
            else:
                row['tag_json'] = row['tag_json'].replace("to_be_fill_max", str(max(valueToBeFill))).replace("to_be_fill_min", str(min(valueToBeFill)))
        elif 'square feet' in row['tag_text'] or 'square feet area' in row['tag_text']:
            is_greater = True
            for word in useful_words:
                if 'less' in word:
                    is_greater = False
                intValue = text2int(word)
                print intValue
                if intValue:
                    valueToBeFill.append(intValue)
            if not sentence_pos_tone:
                is_greater = not is_greater
            if len(valueToBeFill)!=0:
                if not is_greater:
                    row['tag_json'] = row['tag_json'].replace("area_id_to_be_fill","builtup_area_max").replace("to_be_fill", str(max(valueToBeFill)))
                else:
                    row['tag_json'] = row['tag_json'].replace("area_id_to_be_fill","builtup_area_min").replace("to_be_fill", str(min(valueToBeFill)))

        rowJson = json.loads(row['tag_json'])
        for key in rowJson:
            strQuery = "INSERT INTO session_tags (session_id, tag_key, tag_value) VALUES ('"+ session_id +"', '"+ key +"', '"+ rowJson[key] +"') ON DUPLICATE KEY UPDATE tag_value=VALUES(tag_value)"
            #print strQuery
            db.execute(strQuery)

    strQuery = "select tag_key, tag_value from session_tags where session_id = '" + session_id + "'"
    print strQuery
    #self.write(strQuery)
    rows = db.query(strQuery)
    url = "https://www.commonfloor.com/listing-search?"
    
    queryString = ""
    doneParamList = []
    for row in rows:
        queryString = queryString + row['tag_key'] + "=" + row['tag_value'] + "&"
        doneParamList.append(row['tag_key'])

    nextQuery = checkNextQuery(doneParamList)

    url = url + queryString[:-1]
    jsonURL = {"url" : url, "nextQuery":nextQuery}
    #print self.text2int("seven billion one hundred million thirty one thousand three hundred thirty seven")
    db.close()

    last_intent = 'requirementIntent'

    return jsonURL

def restIntent(sentence, pos_tags):
    # train = [
    #         ("Yes please prioritize it", 'prioritizeIntent'),
    #         ("Show me the second one", 'listingIntent'),
    #         ('Can you show me some pictures', 'picturesIntent'),
    #         ('Can you show me some pictures of this house', 'picturesIntent'),
    #         ('Can you show the pictures again','picturesIntent'),
    #         ('Can you show the pictures of the house again','picturesIntent'),
    #         ('Give me the tour of this locality','tourIntent'),
    #         ('I like this house','likeHouseIntent'),
    #         ('Sure Please call the owner','callOwnerIntent')
    #     ]

    intent = cl.classify(sentence)
    if intent == 'listingIntent':
        return listingIntent(sentence, pos_tags)
    elif intent == 'picturesIntent':
        return picturesIntent(sentence, pos_tags)
    elif intent == 'likeHouseIntent':
        return likeHouseIntent()
    elif intent == 'tourIntent':
        return tourIntent(sentence, pos_tags)
    elif intent == 'callOwnerIntent':
        return callOwnerIntent(sentence)
    elif intent == 'prioritizeIntent':
        return prioritizeIntent(sentence)
    else:
        print 'invalid intent'

def listingIntent(sentence, pos_tags):
    global last_url
    global last_intent
    global last_listing_id
    global last_listing_url
    response = {}

    entry_num_word = None
    for tag in pos_tags:
        if(tag[1].startswith('JJ')):
            entry_num_word = tag[0].strip().lower()
            break

    if entry_num_word:
        number = ordinal2Int(entry_num_word)
        #print "last_url ---------> ", last_url
        #print number

        response_listing_link = api_call.listing_link(last_url, int(number))

        #print "listing_url response -> ", response_listing_link
        response['url'] = response_listing_link['url']
        last_listing_url = response['url']
        response['speechText'] = response_listing_link['desc']
        last_listing_id = response_listing_link['listingID']
        last_intent = 'listingIntent'
    else:
        response['speechText'] = "Sorry I didn't understand your statement, can you please say it again."
    
    print "in ListingHandler"
    return response

def ordinal2Int(argument):
    switcher = {
        "first":"1",
        "second":"2",
        "third":"3",
        "fourth":"4",
    }
    return switcher.get(argument, None)


def picturesIntent(sentence, pos_tags):
    global last_intent
    global last_listing_id
    global pic_urls
    response = {}

    if last_intent == 'listingIntent':
        for tag in pos_tags:
            if (tag[0] == 'pictures'):
                #print number
                if last_listing_id:
                    response_pictures_link = api_call.slide_show(last_listing_id)

                    #print "response_pictures_link response -> ", response_pictures_link
                    pic_urls = response_pictures_link

                    response['url'] = "http://stageaira.commonfloor.com:8888/pictures"
                    response['speechText'] = "Please have a look at the pictures. Do you want to have a tour of this property?"
            else:
                response['speechText'] = "Sorry I didn't understand your statement, can you please say it again."
    else:
        response['speechText'] = "Sorry I didn't understand your statement, can you please say it again."

    print "in picturesIntent"
    return response

def likeHouseIntent():
    response = {}

    if last_intent == 'listingIntent':
        response['speechText'] = "Sure. Do you want me to call the owner on your behalf"

    print "in likeHouseIntent"
    return response

def tourIntent(sentence, pos_tags):
    global last_intent
    global last_listing_id
    global pic_urls
    global last_listing_url
    response = {}

    if last_intent == 'listingIntent':
        if 'tour' in sentence:
            if last_listing_url:
                response['url'] = last_listing_url + "#location-map"
                response['speechText'] = "Sure. Please have a look at this locality and let me know if you are interested in this place?"
    else:
        print "here 7"
        response['speechText'] = "Sorry I didn't understand your statement, can you please say it again."

    print "in tourIntent"
    return response

def callOwnerIntent(sentence):
    response = {}

    if last_intent == 'listingIntent':
        api_call.know_conf();
        response['speechText'] = "Thank you. Hope my service was useful to you. Common Floor is helping customers find their dream house using state of the art technology. Hope we talk again soon. Good bye."

    print "in callOwnerIntent"
    return response

def prioritizeIntent(sentence):
    print "in prioritizeIntent"


def text2int(text_num,numwords={}):
        try:
            str_num = str(int(text_num))
            return str_num
        except Exception, e:
            if not numwords:
              units = [
                "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
                "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
                "sixteen", "seventeen", "eighteen", "nineteen",
              ]

              tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

              scales = ["hundred", "thousand", "million", "billion", "trillion"]

              numwords["and"] = (1, 0)
              for idx, word in enumerate(units):    numwords[word] = (1, idx)
              for idx, word in enumerate(tens):     numwords[word] = (1, idx * 10)
              for idx, word in enumerate(scales):   numwords[word] = (10 ** (idx * 3 or 2), 0)

            current = result = 0
            print str(text_num)
            for word in text_num.split():
                if word not in numwords:
                    return None

                scale, increment = numwords[word]
                current = current * scale + increment
                if scale > 100:
                    result += current
                    current = 0

            return str(result + current)

class MessageBuffer(object):
    def __init__(self):
        self.waiters = set()
        self.cache = []
        self.cache_size = 200

    def wait_for_messages(self, cursor=None):
        # Construct a Future to return to our caller.  This allows
        # wait_for_messages to be yielded from a coroutine even though
        # it is not a coroutine itself.  We will set the result of the
        # Future when results are available.
        result_future = Future()
        if cursor:
            new_count = 0
            for msg in reversed(self.cache):
                if msg["id"] == cursor:
                    break
                new_count += 1
            if new_count:
                result_future.set_result(self.cache[-new_count:])
                return result_future
        self.waiters.add(result_future)
        return result_future

    def cancel_wait(self, future):
        self.waiters.remove(future)
        # Set an empty result to unblock any coroutines waiting.
        future.set_result([])

    def new_messages(self, messages):
        logging.info("Sending new message to %r listeners", len(self.waiters))
        for future in self.waiters:
            future.set_result(messages)
        self.waiters = set()
        self.cache.extend(messages)
        if len(self.cache) > self.cache_size:
            self.cache = self.cache[-self.cache_size:]


# Making this a non-singleton is left as an exercise for the reader.
#global_message_buffer = MessageBuffer()

class MessageStartHandler(tornado.web.RequestHandler):
    def post(self):
        print 'here'
        global global_message_buffer

        message = {
            "id": str(uuid.uuid4()),
            "body": "Hello, I am AIRA. Can you help me with your name please?",
            "time": datetime.now().strftime('%H:%M'),
        }
        # to_basestring is necessary for Python 3's json encoder,
        # which doesn't accept byte strings.
        html = "<div class='message' id='m" + message['id'] +"'>"
        html += "<li class='left clearfix'><span class='chat-img pull-left'>"
        html += "<img src='https://www.commonfloor.com/cfassets/logo.png' alt='Commonfloor' class='img-circle' />"
        html += "</span><div class='chat-body clearfix'><div class='header'>"
        html += "<strong class='primary-font'>CommonFloor:</strong> <small class='pull-right text-muted'>"
        html += "<span class='glyphicon glyphicon-time'></span>" + message['time'] + "</small></div>"
        html += "<p>" + message['body'] + "</p></div></li></div>"
        #message["html"] = "<b>" + tornado.escape.to_basestring(self.render_string("message.html", message=message)) + "</b>"
        message["html"] = html
        if self.get_argument("next", None):
            self.redirect(self.get_argument("next"))
        else:
            self.write(message)
        global_message_buffer.new_messages([message])

class MessageResponseHandler(tornado.web.RequestHandler):
    def post(self):
        global global_message_buffer
        global last_answer
        question = self.get_argument("body")
        #logic to build for decision tree
        answer = ""
        if question == '1':
            if 'Shortlist' in last_answer:
                answer = "Ok. So you have selected a listing. Do you want to enquire about home loan. Tell me your query regarding home loan?"
        elif 'yes' in question:
            if 'better project' in last_answer:
                answer = "Okay..Let me show you some good property's listings.<br />" + query.property_images_in_chat()
        else:
            answer = query.query_str(question)

        last_answer = answer
        # if 'better projects' in answer:
        #     if 'yes' in question:
        #         answer = "Okay..Let me show you some good properties"
        #answer = str(query.graph_query_str(question))

        message = {
            "id": str(uuid.uuid4()),
            "body": answer,
            "time": datetime.now().strftime('%H:%M'),
        }
        if message['body'] is None:
            message['body'] = 'Sorry I didn;t find any result for your query.'
        # to_basestring is necessary for Python 3's json encoder,
        # which doesn't accept byte strings.
        html = "<div class='message' id='m" + message['id'] +"'>"
        html += "<li class='left clearfix'><span class='chat-img pull-left'>"
        html += "<img src='https://www.commonfloor.com/cfassets/logo.png' alt='Commonfloor' class='img-circle' />"
        html += "</span><div class='chat-body clearfix'><div class='header'>"
        html += "<strong class='primary-font'>CommonFloor:</strong> <small class='pull-right text-muted'>"
        html += "<span class='glyphicon glyphicon-time'></span>" + message['time'] + "</small></div>"
        html += "<p>" + message['body'] + "</p></div></li></div>"
        #message["html"] = "<b>" + tornado.escape.to_basestring(self.render_string("message.html", message=message)) + "</b>"
        message["html"] = html
        if self.get_argument("next", None):
            self.redirect(self.get_argument("next"))
        else:
            self.write(message)
        #print 'response message => ', message
        global_message_buffer.new_messages([message])

class MessageNewHandler(tornado.web.RequestHandler):
    def post(self):
        global global_message_buffer
        message = {
            "id": str(uuid.uuid4()),
            "body": self.get_argument("body"),
            "time": datetime.now().strftime('%H:%M'),
        }
        # to_basestring is necessary for Python 3's json encoder,
        # which doesn't accept byte strings.
        html = "<div class='message' id='m" + message['id'] +"'>"
        html += "<li class='left clearfix'><span class='chat-img pull-left'>"
        html += "<img src='https://www.commonfloor.com/public/images/agent_profile/thumb_size/default.png' style='width:35px' alt='you' class='img-circle' />"
        html += "</span><div class='chat-body clearfix'><div class='header'>"
        html += "<strong class='primary-font'>YOU:</strong> <small class='pull-right text-muted'>"
        html += "<span class='glyphicon glyphicon-time'></span>" + message['time'] + "</small></div>"
        html += "<p>" + message['body'] + "</p></div></li></div>"
        #message["html"] = tornado.escape.to_basestring(self.render_string("message.html", message=message))
        message["html"] = html
        if self.get_argument("next", None):
            self.redirect(self.get_argument("next"))
        else:
            self.write(message)
        #print message
        global_message_buffer.new_messages([message])
        #print global_message_buffer.cache

class MessageUpdatesHandler(tornado.web.RequestHandler):
    @gen.coroutine
    def post(self):
        global global_message_buffer
        cursor = self.get_argument("cursor", None)
        # Save the future returned by wait_for_messages so we can cancel
        # it in wait_for_messages
        try:
            self.future = global_message_buffer.wait_for_messages(cursor=cursor)
            messages = yield self.future
            if self.request.connection.stream.closed():
                return
            self.write(dict(messages=messages))
        except Exception, e:
            print "Exception happen in message update"

    def on_connection_close(self):
        global_message_buffer.cancel_wait(self.future)

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/a/message/new", MessageNewHandler),
            (r"/a/message/start", MessageStartHandler),
            (r"/a/message/response", MessageResponseHandler),
            (r"/a/message/updates", MessageUpdatesHandler),
            (r"/hello", HelloHandler),
            (r"/url", NewURLHandler),
            (r"/intent", GetIntentHandler),
            (r"/posts", DBHandler),
            (r"/pictures", PicturesHandler),
            (r"/start", StartHandler),
            (r"/parser", ParseHandler),
            (r"/query", AnswerHandler),
            (r"/knowledgeBase", UnstructuredDataHandler),
            (r"/relation",CreateRelationshipHandler),
            (r"/structure_query",StrcutureAnswerHandler),
            (r"/summarizationHandler", SummarizationHandler),
            (r"/chatbox", ChatBoxHandler),
        ]
        settings = {
            "template_path":os.path.join(os.path.dirname(__file__), "templates"),
            "static_path":adminSettings.STATIC_PATH,
            "debug":adminSettings.DEBUG,
            "cookie_secret": adminSettings.COOKIE_SECRET,
        }
        tornado.web.Application.__init__(self, handlers, **settings)

def main():
    print "server started **********"
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()
    

if __name__ == "__main__":
    main()
