import tornado.auth
import tornado.escape
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import adminSettings
import os.path
import torndb
from datetime import datetime
import time

from tornado.options import define, options

from py2neo import authenticate, Graph
from py2neo import Node, Relationship
from py2neo import error
from lxml import html
import requests

import math
import logging
from textblob import TextBlob

import query

import nltk
from nltk.parse import stanford

define("port", default=8889, help="run on the given port", type=int)
define("host", default="localhost", help="host")
define("database", default="aira", help="database")
define("user", default="cfx_user", help="user")
define("password", default="cfx_user@123", help="password")

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        return self.get_secure_cookie("user")

class MainHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        username = tornado.escape.xhtml_escape(self.current_user)
        print 'username => ', username
        self.render("index.html", username = username)

class AuthRegisterHandler(BaseHandler):
    def get(self):
        try:
            errormessage = self.get_argument("error")
        except:
            errormessage = ""
        self.render("register.html", errormessage = errormessage)
    def post(self):
        username = self.get_argument("username")
        confirm_password_1 = self.get_argument("confirm_password_1")
        confirm_password_2 = self.get_argument("confirm_password_2")
        if confirm_password_1==confirm_password_2:
            try:
                db = torndb.Connection(options.host, options.database, options.user, options.password)
                strQuery = "INSERT INTO admin_users (username, password, created_date) VALUES ('"+ username +"', '"+ confirm_password_1 +"', '"+ datetime.now().strftime('%Y-%m-%d %H:%M:%S') +"')"
                #print strQuery
                db.execute(strQuery)
                self.set_current_user(username)
                self.redirect(self.get_argument("next", u"/"))
            except Exception, e:
                print e
                error_msg = u"?error=" + tornado.escape.url_escape("Username already exists.")
                self.redirect(u"/register" + error_msg)
        else:
            error_msg = u"?error=" + tornado.escape.url_escape("Please enter correct password to match")
            self.redirect(u"/register" + error_msg)

        # self.render("register.html")

class AuthLoginHandler(BaseHandler):
    def get(self):
        try:
            errormessage = self.get_argument("error")
        except:
            errormessage = ""
        self.render("login.html", errormessage = errormessage)

    def check_permission(self, password, username):
        db = torndb.Connection(options.host, options.database, options.user, options.password)
        rows = db.query("select count(*) as count from admin_users where username='" + username + "' and password='" + password + "'")
        #print strQuery
        db.close()
        if int(rows[0]["count"])==1:
            return True
        return False

    def post(self):
        username = self.get_argument("username", "")
        password = self.get_argument("password", "")
        auth = self.check_permission(password, username)
        if auth:
            self.set_current_user(username)
            self.redirect(self.get_argument("next", u"/"))
        else:
            error_msg = u"?error=" + tornado.escape.url_escape("Login incorrect")
            self.redirect(u"/auth/login/" + error_msg)

    def set_current_user(self, user):
        if user:
            self.set_secure_cookie("user", tornado.escape.json_encode(user))
        else:
            self.clear_cookie("user")

class AuthLogoutHandler(BaseHandler):
    def post(self):
        self.clear_cookie("user")
        self.redirect(self.get_argument("next", "/"))

class CreateStructureRelationshipHandler(tornado.web.RequestHandler):
    def rep(self, group_sent):
        try:
            payload = json.dumps({"text": group_sent})
            r = requests.post('https://api.spacy.io/api/displacy/parse/',data=payload)
            word_replacer = ''
            word_vec = json.loads(r.text)['words']
            if word_vec[0]['tag']=='NOUN' or word_vec[0]['tag']=='NNP':
                word_replacer = word_vec[0]['word']
            elif word_vec[1]['tag']=='NNP' or word_vec[1]['tag']=='NOUN':
                word_replacer = word_vec[1]['word']
            if  len(word_replacer)>1:
                i = 0
                while word_vec[i]['word']!='.' and word_vec[i]['word']!='?' and word_vec[i]['word']!='!':
                    i = i + 1
                if len(word_vec)>i and word_vec[i+1]['tag']=='NOUN':
                    print "ues"
                    word_vec[i+1]['word'] = word_replacer
            return " ".join([each['word'] for each in word_vec])
        except Exception as e:
            return group_sent

    def add_relations(self, line, first_node, second_node, negative_line, url, page_title=None,verb_added=None):
        global predicate_word_for_a_line
        global logs
        print 'in add relation line => ', line , ', first_node => ', first_node, ' second_node => ', second_node
        authenticate("localhost:7474", "neo4j", "maxheap123")
        g = Graph()
        verbs = []
        if not verb_added:
            first_index = line.index(first_node)
            second_index = line.index(second_node)
            used_line = line[first_index+len(first_node):second_index]
            list_of_words = nltk.word_tokenize(used_line)
            pos_tags = nltk.pos_tag(list_of_words)
            verb_word = ""
            for tag in pos_tags:
                if tag[1][:2] == 'VB' and len(tag[0]) != 1:
                    verb_word += tag[0].lower() + "_"
                else:
                    if verb_word!="":
                        if verb_word[:-1] not in verbs:
                            verbs.append(verb_word[:-1])
                        verb_word = ""

            if verb_word!="":
                if verb_word[:-1] not in verbs:
                    verbs.append(verb_word[:-1])
                
            print 'in add relation verbs ---------------------> ', str(verbs)
        else:
            verbs.append(verb_added)

        verb_len = len(verbs)
        if verb_len!=0:
            verb = '_'.join(verbs)
            #for verb in verbs:
            logs.append("<b>Relationship added => </b> (" + first_node + ") => (" + verb + ") => (" + second_node+ ")<br />")
            strQuery = ""
            if negative_line==True:
                strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ verb +"{sentence:'" + line + "',neg:True,page_title:'" + page_title + "',url:'" + url + "',time_created:'" + str(time.time()) + "'}]->(b) RETURN r"
            else:
                strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ verb +"{sentence:'" + line + "',page_title:'" + page_title + "',url:'" + url + "',time_created:'" + str(time.time()) + "'}]->(b) RETURN r"
            for record in g.cypher.execute(strQuery):
                print 'record'
        else:
            if predicate_word_for_a_line == "":
                print "********************************"
                list_of_words = nltk.word_tokenize(line)
                pos_tags = nltk.pos_tag(list_of_words)
                verb_word = ""
                for tag in pos_tags:
                    if tag[1][:2] == 'VB' and len(tag[0]) != 1:
                        verb_word = tag[0].lower()
                        break
                predicate_word_for_a_line = verb_word
                print "********************************"
            if predicate_word_for_a_line != "":
                strQuery = ""
                logs.append("<b>Relationship added => </b> (" + first_node + ") => (" + predicate_word_for_a_line + ") => (" + second_node+ ")<br />")
                if negative_line==True:
                    strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ predicate_word_for_a_line +"{sentence:'" + line + "',neg:True,page_title:'" + page_title + "',url:'" + url + "',time_created:'" + str(time.time()) + "'}]->(b) RETURN r"
                else:
                    strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ predicate_word_for_a_line +"{sentence:'" + line + "',page_title:'" + page_title + "',url:'" + url + "',time_created:'" + str(time.time()) + "'}]->(b) RETURN r"
                for record in g.cypher.execute(strQuery):
                    print 'record'


    def strip_non_ascii(self, string):
        ''' Returns the string without non ASCII characters'''
        stripped = (c for c in string if 0 < ord(c) < 127)
        return ''.join(stripped)

    def get(self):
        # main_url = 'https://www.commonfloor.com/guide/category/real-estate/home-loan'
        # count = 1
        # page_link = []
        # while count<2:
        #     if count==1:
        #         url = main_url
        #     else:
        #         url = main_url + "/page/" + str(count)
        #     count += 1
        #     page = requests.get(url)
        #     tree = html.fromstring(page.text)
        #     t = tree.xpath("//div[@class='postmiddlebg']//h3//a/@href")
        #     for elem in t:
        #         page_link.append(str(self.strip_non_ascii(elem).lower().encode('utf-8')))

        # print 'page_link => ', page_link
        print self.rep('Sumit is a good boy. He is very helpful')
        return

    def post(self):
        global logs
        global predicate_word_for_a_line
        #global provided_url

        logs = []
        authenticate("localhost:7474", "neo4j", "maxheap123")
        g = Graph()
        print self.request.arguments
        main_url=self.get_argument('url', 'No data received')
        print main_url
        count = 1
        page_link = []
        from lxml import html
        import requests
        while count<14:
            if count==1:
                page_url = main_url
            else:
                page_url = main_url + "/page/" + str(count)

            print 'page_url => ', page_url
            count += 1
            page = requests.get(page_url)
            tree = html.fromstring(page.text)
            t = tree.xpath("//div[@class='postmiddlebg']//h3//a/@href")
            for elem in t:
                page_link.append(str(self.strip_non_ascii(elem).lower().encode('utf-8')))
        
        for link in page_link:
            print '*********************************************** link is => ', link
            url = link
            page = requests.get(url)
            tree = html.fromstring(page.text)
            #t = tree.xpath("//p[@style='text-align: justify;']")
            t = tree.xpath("//div[@class='fulldetal_content hyphenate']//p")
            t1 = tree.xpath("//div[@class='fulldetal_content hyphenate']//p//span")
            page_title_elem = tree.xpath("//h1[@class='page_heading']")

            page_title =""
            for elem in page_title_elem:
                for txt in elem.xpath('text()'):
                    page_title += str(self.strip_non_ascii(txt).strip().encode('utf-8'))

            #print 'page_title => ', page_title

            whole_text = ""
            for elem in t:
                for txt in elem.xpath('text()'):
                    whole_text += str(self.strip_non_ascii(txt).lower().encode('utf-8')) + " "

            for elem in t1:
                for txt in elem.xpath('text()'):
                    whole_text += str(self.strip_non_ascii(txt).lower().encode('utf-8')) + " "

            #print whole_text

            tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
            sentences = tokenizer.tokenize(whole_text)

            existing_nodes = []
            for record in g.cypher.execute("MATCH n RETURN n.name"):
                existing_nodes.append(record[0])

            print str(existing_nodes)

            counter = 0
            last_line = ''
            for line in sentences:
                original_line = line
                converted_line = ''
                if last_line != '':
                    group_txt = last_line + " " + line
                    print 'group_txt -> ', group_txt
                    print 'original line -> ', line
                    converted_txt =  self.rep(group_txt)
                    line = converted_txt[len(last_line):]
                    print 'converted line -> ', line

                predicate_word_for_a_line = ""
                counter += 1
                print "(", counter ,")", line
                if line:
                    list_of_words = nltk.word_tokenize(line)
                    pos_tags = nltk.pos_tag(list_of_words)
                    print pos_tags

                    testimonial = TextBlob(line)
                    polarity = testimonial.sentiment.polarity
                    negative_line = False
                    if polarity<0:
                        negative_line = True

                    intersection_words = []
                    for node in existing_nodes:
                        if node in line:
                            intersection_words.append(node)

                    #print 'before intersection_words filtering -> ', intersection_words
                    filtered_interesection_words = list(intersection_words)
                    for intersection_word_1 in intersection_words:
                        for intersection_word_2 in intersection_words:
                            if (intersection_word_1!=intersection_word_2):
                                if (intersection_word_1 in intersection_word_2):
                                    if intersection_word_1 in filtered_interesection_words:
                                        filtered_interesection_words.remove(intersection_word_1)


                    len_words = len(filtered_interesection_words)
                    if len_words>1:
                        print 'verb'
                        for first_node in filtered_interesection_words:
                            for second_node in filtered_interesection_words:
                                if line.index(first_node)<line.index(second_node):
                                    self.add_relations(line, first_node, second_node, negative_line, url, page_title)
                        #find verb
                    elif len_words==1:
                        second_node = filtered_interesection_words[0]
                        self.add_relations(line, "home loan", second_node, negative_line, url, page_title, 'contains')
                    else:
                        print 'unmatched sentence is -> ', line

                    print 'intersection_words -> ', len(filtered_interesection_words)
                
                last_line = line
        self.render("relation.html", logs=logs)

class AddNodeHandler(tornado.web.RequestHandler):
    def add_relations(self, line, first_node, second_node, negative_line, url, page_title=None,verb_added=None):
        global predicate_word_for_a_line
        global logs
        predicate_word_for_a_line == ""
        print 'in add relation line => ', line , ', first_node => ', first_node, ' second_node => ', second_node
        authenticate("localhost:7474", "neo4j", "maxheap123")
        g = Graph()
        verbs = []
        if not verb_added:
            first_index = line.index(first_node)
            second_index = line.index(second_node)
            used_line = line[first_index+len(first_node):second_index]
            list_of_words = nltk.word_tokenize(used_line)
            pos_tags = nltk.pos_tag(list_of_words)
            verb_word = ""
            for tag in pos_tags:
                if tag[1][:2] == 'VB' and len(tag[0]) != 1:
                    verb_word += tag[0].lower() + "_"
                else:
                    if verb_word!="":
                        if verb_word[:-1] not in verbs:
                            verbs.append(verb_word[:-1])
                        verb_word = ""

            if verb_word!="":
                if verb_word[:-1] not in verbs:
                    verbs.append(verb_word[:-1])
                
            print 'in add relation verbs ---------------------> ', str(verbs)
        else:
            verbs.append(verb_added)

        verb_len = len(verbs)
        if verb_len!=0:
            verb = '_'.join(verbs)
            #for verb in verbs:
            logs.append("<b>Relationship added => </b> (" + first_node + ") => (" + verb + ") => (" + second_node+ ")<br />")
            strQuery = ""
            if negative_line==True:
                strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ verb +"{sentence:'" + line + "',neg:True,page_title:'" + page_title + "',url:'" + url + "',time_created:'" + str(time.time()) + "'}]->(b) RETURN r"
            else:
                strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ verb +"{sentence:'" + line + "',page_title:'" + page_title + "',url:'" + url + "',time_created:'" + str(time.time()) + "'}]->(b) RETURN r"
            for record in g.cypher.execute(strQuery):
                print 'record'
        else:
            if predicate_word_for_a_line == "":
                print "********************************"
                list_of_words = nltk.word_tokenize(line)
                pos_tags = nltk.pos_tag(list_of_words)
                verb_word = ""
                for tag in pos_tags:
                    if tag[1][:2] == 'VB' and len(tag[0]) != 1:
                        verb_word = tag[0].lower()
                        break
                predicate_word_for_a_line = verb_word
                print "********************************"
            if predicate_word_for_a_line != "":
                strQuery = ""
                logs.append("<b>Relationship added => </b> (" + first_node + ") => (" + predicate_word_for_a_line + ") => (" + second_node+ ")<br />")
                if negative_line==True:
                    strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ predicate_word_for_a_line +"{sentence:'" + line + "',neg:True,page_title:'" + page_title + "',url:'" + url + "',time_created:'" + str(time.time()) + "'}]->(b) RETURN r"
                else:
                    strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ predicate_word_for_a_line +"{sentence:'" + line + "',page_title:'" + page_title + "',url:'" + url + "',time_created:'" + str(time.time()) + "'}]->(b) RETURN r"
                for record in g.cypher.execute(strQuery):
                    print 'record'


    def strip_non_ascii(self, string):
        ''' Returns the string without non ASCII characters'''
        stripped = (c for c in string if 0 < ord(c) < 127)
        return ''.join(stripped)

    def get(self):
        self.render("add_node.html",existing_nodes= None, existing_relations=None, error_message=None, show_messages=None)

    def post(self):
        global logs
        global predicate_word_for_a_line
        authenticate("localhost:7474", "neo4j", "maxheap123")
        g = Graph()

        if 'searchNodeAndRelation' in self.request.arguments:
            existing_nodes = []
            existing_relations = []
            search_txt = self.get_argument('node')

            for record in g.cypher.execute("MATCH n where n.name=~'.*"+ search_txt +".*' return n.name"):
                existing_nodes.append(str(record[0]))

            for record in g.cypher.execute("MATCH ()-[r]->() where type(r)=~'.*"+ search_txt +".*' return type(r)"):
                existing_relations.append(str(record[0]))
            self.render("add_node.html",existing_nodes= existing_nodes, existing_relations=existing_relations, error_message=None, show_messages=None)

        elif 'addNodeAndRelations' in self.request.arguments:
            new_node_txt = self.get_argument('new_nodes_txt').strip().lower()
            main_url=self.get_argument('url', 'No data received')
            print main_url
            is_exist = False
            for record in g.cypher.execute("MATCH n where n.name=~'"+ new_node_txt +"' return n.name"):
                if record[0] is not None:
                    is_exist = True
            if is_exist:
                self.render("add_node.html",existing_nodes= None, existing_relations=None, error_message='Node already existing',show_messages=None)
            else:
                logs = []
                count = 1
                page_link = []
                while count<14:
                    if count==1:
                        page_url = main_url
                    else:
                        page_url = main_url + "/page/" + str(count)

                    print 'page_url => ', page_url
                    count += 1
                    page = requests.get(page_url)
                    tree = html.fromstring(page.text)
                    t = tree.xpath("//div[@class='postmiddlebg']//h3//a/@href")
                    for elem in t:
                        page_link.append(str(self.strip_non_ascii(elem).lower().encode('utf-8')))
                
                existing_nodes = []
                for record in g.cypher.execute("MATCH n RETURN n.name"):
                    existing_nodes.append(record[0])
                #print str(existing_nodes)

                newNode = Node("Subject", name=new_node_txt)
                try:
                    #print new_node.strip().lower()
                    g.create(newNode)
                except Exception as e:
                    #print e
                    pass

                for link in page_link:
                    #print '*********************************************** link is => ', link
                    url = link
                    page = requests.get(url)
                    tree = html.fromstring(page.text)
                    #t = tree.xpath("//p[@style='text-align: justify;']")
                    t = tree.xpath("//div[@class='fulldetal_content hyphenate']//p")
                    t1 = tree.xpath("//div[@class='fulldetal_content hyphenate']//p//span")
                    page_title_elem = tree.xpath("//h1[@class='page_heading']")

                    page_title =""
                    for elem in page_title_elem:
                        for txt in elem.xpath('text()'):
                            page_title += str(self.strip_non_ascii(txt).strip().encode('utf-8'))

                    #print 'page_title => ', page_title

                    whole_text = ""
                    for elem in t:
                        for txt in elem.xpath('text()'):
                            whole_text += str(self.strip_non_ascii(txt).lower().encode('utf-8')) + " "

                    for elem in t1:
                        for txt in elem.xpath('text()'):
                            whole_text += str(self.strip_non_ascii(txt).lower().encode('utf-8')) + " "

                    #print whole_text

                    tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
                    sentences = tokenizer.tokenize(whole_text)

                    counter = 0
                    for line in sentences:
                        if line and (new_node_txt in line):
                            print '*********************************************** link is => ', link
                            predicate_word_for_a_line = ''
                            counter += 1
                            list_of_words = nltk.word_tokenize(line)
                            pos_tags = nltk.pos_tag(list_of_words)
                            print pos_tags

                            testimonial = TextBlob(line)
                            polarity = testimonial.sentiment.polarity
                            negative_line = False
                            if polarity<0:
                                negative_line = True

                            intersection_words = []
                            for node in existing_nodes:
                                if node in line:
                                    intersection_words.append(node)

                            #print 'before intersection_words filtering -> ', intersection_words
                            filtered_interesection_words = list(intersection_words)
                            for intersection_word_1 in intersection_words:
                                for intersection_word_2 in intersection_words:
                                    if (intersection_word_1!=intersection_word_2):
                                        if (intersection_word_1 in intersection_word_2):
                                            if intersection_word_1 in filtered_interesection_words:
                                                filtered_interesection_words.remove(intersection_word_1)


                            len_words = len(filtered_interesection_words)
                            if len_words>0:
                                print 'verb'
                                for second_node in filtered_interesection_words:
                                    self.add_relations(line, new_node_txt, second_node, negative_line, url, page_title)
                                #find verb
                            elif len_words==0:
                                self.add_relations(line, "home loan", new_node_txt, negative_line, url, page_title, 'contains')
                            else:
                                print 'unmatched sentence is -> ', line

                            print 'intersection_words -> ', len(filtered_interesection_words)

                self.render("add_node.html",existing_nodes= None, existing_relations=None, error_message=None,show_messages=logs)            
            

class FeatureSetHandler(tornado.web.RequestHandler):
    def strip_non_ascii(self, string):
        ''' Returns the string without non ASCII characters'''
        stripped = (c for c in string if 0 < ord(c) < 127)
        return ''.join(stripped)

    def get(self):
        global new_nodes
        global existing_nodes
        global relations

        authenticate("localhost:7474", "neo4j", "maxheap123")
        g = Graph()

        existing_nodes = []
        for record in g.cypher.execute("MATCH n return n.name ORDER BY n.name"):
            existing_nodes.append(str(record[0]))
        relations = []
        for record in g.cypher.execute("MATCH (n)-[r]->(n2) WHERE type(r)=~ 'equals' or type(r)=~ 'not_equals' RETURN n.name as first_node,type(r) as relation,n2.name as second_node"):
            relations.append(record)

        self.render("structured_data.html",existing_nodes= existing_nodes, relations=relations)
    
    def post(self):
        global new_nodes
        global existing_nodes
        global provided_url
        global relations

        authenticate("localhost:7474", "neo4j", "maxheap123")
        g = Graph()
        try:
            g.schema.create_uniqueness_constraint("Subject", "name")
        except:
            pass

        print self.request.arguments
        if 'addNode' in self.request.arguments:
            new_nodes_txt = self.get_argument('new_nodes_txt')
            new_nodes = new_nodes_txt.split('\n')
            #print new_nodes
            for new_node in new_nodes:
                node = Node("Subject", name=new_node.strip().lower())
                try:
                    #print new_node.strip().lower()
                    g.create(node)
                except Exception as e:
                    print e
                    pass

        elif 'reset' in self.request.arguments:
            for record in g.cypher.execute("MATCH (a:Subject) OPTIONAL MATCH (a)-[r1]-() DELETE a,r1"):
                print(record)
        elif 'startParsing' in self.request.arguments:
            url = self.get_argument('url')
            page = requests.get(url)
            tree = html.fromstring(page.text)
            t = tree.xpath("//div[@class='fulldetal_content hyphenate']//p")
            t1 = tree.xpath("//div[@class='fulldetal_content hyphenate']//p//span")
            #t_questions = tree.xpath("//div[@class='fulldetal_content hyphenate']//p//strong")

            whole_text = ""
            for elem in t:
                for txt in elem.xpath('text()'):
                    whole_text += str(self.strip_non_ascii(txt).lower().encode('utf-8')) + " "

            for elem in t1:
                for txt in elem.xpath('text()'):
                    print 'here => ', txt
                    whole_text += str(self.strip_non_ascii(txt).lower().encode('utf-8')) + " "

            # for elem in t_questions:
            #     for txt in elem.xpath('text()'):
            #         whole_text += str(self.strip_non_ascii(txt).lower().encode('utf-8')) + " "

            tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
            sentences = tokenizer.tokenize(whole_text)

            print sentences

            relations = []

            nodes_from_url = []
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

        elif 'select_first_node' in self.request.arguments:
            print self.request.arguments
            if existing_nodes:
                first_node = self.get_argument('select_first_node')
                second_node = self.get_argument('select_second_node')
                similarity_value = self.get_argument('select_similarity')

                similarity = "equals"
                if similarity_value=='!=':
                    similarity = "not_equals"

                strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node + "' AND b.name = '" + second_node + "' CREATE (a)-[r:"+ similarity +"]->(b) RETURN r"
                for record in g.cypher.execute(strQuery):
                        print(record)

        elif 'synonymFirstNodeId' in self.request.arguments:
            print self.request.arguments
            if existing_nodes:
                first_node = self.get_argument('synonymFirstNodeId')
                second_node = self.get_argument('synonymSecondNodeId')
                node = Node("Subject", name=second_node.strip().lower())
                try:
                    #print new_node.strip().lower()
                    g.create(node)
                except Exception as e:
                    print e
                    pass
                similarity_value = self.get_argument('select_similarity')
                similarity = "equals"
                if similarity_value=='!=':
                    similarity = "not_equals"

                first_node_relations = [first_node]
                for record in g.cypher.execute("MATCH (n)-[r]-(n2) WHERE type(r)=~ 'equals' and n.name = '" + first_node + "' RETURN n2.name as similar_nodes"):
                    first_node_relations.append(str(record[0]))

                for first_node_relation in first_node_relations:
                    strQuery = "MATCH (a:Subject),(b:Subject) WHERE a.name = '" + first_node_relation + "' AND b.name = '" + second_node.strip().lower() + "' CREATE (a)-[r:"+ similarity +"]->(b) RETURN r"
                    for record in g.cypher.execute(strQuery):
                        print(record)

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

        existing_nodes = []
        for record in g.cypher.execute("MATCH n return n.name ORDER BY n.name"):
            existing_nodes.append(str(record[0]))

        relations = []
        for record in g.cypher.execute("MATCH (n)-[r]->(n2) WHERE type(r)=~ 'equals' or type(r)=~ 'not_equals' RETURN n.name as first_node,type(r) as relation,n2.name as second_node"):
            relations.append(record)

        self.render("structured_data.html", existing_nodes= existing_nodes, relations=relations)

class CheckQueryHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("check_query.html", result_sentences = None, query=None, titles=None, title_ratings=None)

    def post(self):
        print self.request.arguments
        strQuery = self.get_argument('searchEntity', 'No data received')
        result_json = query.graph_query(strQuery)
        self.render("check_query.html", result_sentences = result_json['result_sentences'], query = strQuery, titles=result_json['titles'])


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/auth/login/", AuthLoginHandler),
            (r"/register", AuthRegisterHandler),
            (r"/auth/logout/", AuthLogoutHandler),
            (r"/add_nodes", FeatureSetHandler),
            (r"/add_single_node", AddNodeHandler),
            (r"/add_relation",CreateStructureRelationshipHandler),
            (r"/check_query",CheckQueryHandler),
        ]
        settings = {
            "template_path":adminSettings.TEMPLATE_PATH,
            "static_path":adminSettings.STATIC_PATH,
            "debug":adminSettings.DEBUG,
            "cookie_secret": adminSettings.COOKIE_SECRET,
            "login_url": "/auth/login/"
        }
        tornado.web.Application.__init__(self, handlers, **settings)

def main():
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()