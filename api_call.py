import requests
import urllib2, json, time
import urllib
import hashlib
from StringIO import StringIO
import gzip

api_key = 'nk8qh4vtri7l3hwotbsdtv2zl3p5u168'

def listing_link(url, number):
    from lxml import html
    import requests
    page = requests.get(url)
    tree = html.fromstring(page.text)
    result = tree.xpath("//*[contains(concat(' ', normalize-space(@data-tracking-id), ' '), '2042')]/@href")

    try:
        if result[number-1]:
            ret_url = "https://www.commonfloor.com"+result[number-1]
    except Exception,e:
        ret_json ={'url':None,'Error':'Index out of range', 'listingID':None}
        return ret_json
    
    page = requests.get(ret_url)
    tree = html.fromstring(page.text)
    description = "".join(tree.xpath("//p[@class='section-description']/text()")).strip()
    import re
    description = re.sub('\s+', ' ', description).encode('ascii','ignore')
    t = tree.xpath("//div[@class='row info-wrap']//span[@class='details-item-key']")
    r = tree.xpath("//div[@class='row info-wrap']//span[@class='details-item-value']")
    details = {}
    for each, each1 in zip(t, r):
        details[str("".join(each.xpath('text()')).strip())]= str("".join(each1.xpath('text()')).strip())
    
    text = "Sure. This is " + description + ", "
    if details.get('Property On:', None):
        text += "This listing has property on " + details.get('Property On:') + ", "
    # if details.get('Facing:', None):
    #     text += "Facing " + details.get('Facing:') + ", "
    # if details.get('Carpet Area:', None):
    #     temp = details.get('Carpet Area:')
    #     text += str("".join(re.findall(r'\d+', temp))) + " square feet in carpet area, "
    # if details.get('Parking Available:', None):
    #     text += "Parking Available, "    
    # if details.get('Flooring:', None):
    #     text += details.get('Flooring:') + ", Do you want to look for the pictures of this flat? "   

    ret_json ={'url':ret_url,'desc':text, 'listingID':ret_url.split('/')[-1]}
    return ret_json

def know_conf():
    url = "http://dev.knowlarity.com/api/voice/quickCall/?username=sumit786raj@gmail.com&password=000786&ivr_id=1000004589&phone_book=9035932384&format=xml"
    import requests
    r = requests.get(url)
    return r.text

def slide_show(listing_id):
    import ast
    print listing_id," <-- listing_id from slide_show"
    pic_urls = ast.literal_eval(getListingImages(str(listing_id)))
    return pic_urls
    #return render("url.html", data_urls = pic_urls)
    #return render_template('index.html', data_urls = pic_urls)

def getListingImages(listing_id):
    print "get Listing Images"
    base_url = "http://www.commonfloor.com/api/listing-v2/get-listing-details?listing_id=" + listing_id
    url = base_url + '?api_key=' + api_key
    post_params = None
    ts = str(int(time.time()))
    secure_hash = getSecureHash(url, post_params, api_key, ts)

    sender_url = base_url + '&sign=' + str(secure_hash) + '&timestamp=' + ts
    print 'secure_url --------> ',sender_url
    
    request = urllib2.Request(sender_url)
    request.add_header('Accept-encoding', 'gzip')
    response = urllib2.urlopen(request)
    if response.info().get('Content-Encoding') == 'gzip':
        buf = StringIO(response.read())
        f = gzip.GzipFile(fileobj=buf)
        response_api_val = f.read()

    #removing extra script
    if '<' in response_api_val:
        response_api_val = response_api_val[:response_api_val.index('<')]
    #end removing extra script

    result_json = json.loads(response_api_val)
    
    print result_json["results"]["images"]["full"]

    return json.dumps(result_json["results"]["images"]["full"])

def getSecureHash(url,post_params,api_key, ts):
    if post_params is not None:
        url = url + "&"+post_params

    split_url = url.split('?')
    base_url = split_url[0];

    params=[]
    if len(split_url) > 1:
        params=split_url[1].split("&")
    #print 'params',params
    query_map={}
    if len(params) > 0:
        for param in params:
            param_split=param.split('=')
            query_map.update({param_split[0]:param_split[1]})

        # add time stamp if any param exists
        query_map.update({'timestamp':ts})

    keys = query_map.keys()
    keys.sort()
    new_url = '?'
    if('api_key' in keys):
        keys.remove('api_key') # remove the key such that we can add the api key later on manually
    for key in keys:
       new_url += urllib.urlencode({key:query_map.get(key)})+'&'
    print 'new_url', new_url
    new_url_with_key = new_url + 'api_key='+api_key
    md5_seed_url= base_url + new_url_with_key
    md5_hash = hashlib.md5(md5_seed_url).hexdigest()
    print 'md5_seed_url',md5_seed_url

    return md5_hash