import chardet
import urllib.request
from urllib.parse import urlparse
from urllib.parse import urljoin
from lxml import etree
from fake_useragent import UserAgent
import re


class ExtractContent(object):

    def __init__(self):
        self.score = 5
        self.length = 5
        self.ua = UserAgent()
        self.ua_type = 'random'

    # 获得html响应
    def get_html(self, url):
        url_parse = urlparse(url)

        # 获得uaer_agent
        def get_ua():
            return getattr(self.ua, self.ua_type)

        headers = {
            "User-Agent": get_ua(),
            "Referer": "{}://{}".format(url_parse.scheme, url_parse.netloc),
        }
        request = urllib.request.Request(url=url, headers=headers)
        response = urllib.request.urlopen(request)
        result = response.read()
        code_detect = chardet.detect(result)['encoding']
        if code_detect:
            html = result.decode(code_detect, 'ignore')
        else:
            html = result.decode("utf-8", 'ignore')
        return html

    # 获得新闻的标题
    def get_title(self, html):
        selector = etree.HTML(html)
        title = selector.xpath('//title/text()')
        if title:
            title = title[0].strip()
        else:
            title = ""
        return title

    # 获得下一页链接
    def get_next_url(self, html):
        next_url_tag = False
        next_url = []
        selector = etree.HTML(html)
        url_nodes = selector.xpath("//a")
        for url_node in url_nodes:
            text = url_node.xpath('./text()')
            if text:
                tmp_text = text[0].replace(" ", "").replace("\t", "")
                if tmp_text == "下一页":
                    next_url_tag = True
                    next_url = url_node.xpath('./@href')
                if next_url_tag:
                    break
        if next_url:
                if "javascript" in next_url[0]:
                    return False, None
                else:
                    return next_url_tag, urljoin(url, next_url[0])
        return next_url_tag, None

    def replace_char_entity(self, htmlstr):
        CHAR_ENTITIES = {'nbsp': ' ',
                         '160': ' ',
                         'lt': '<',
                         '60': '<',
                         'gt': '>',
                         '62': '>',
                         'amp': '&',
                         '38': '&',
                         'quot': '"',
                         '34': '"', }
        re_charEntity = re.compile(r'&#?(?P<name>\w+);')
        sz = re_charEntity.search(htmlstr)
        while sz:
            entity = sz.group()
            key = sz.group('name')
            try:
                htmlstr = re_charEntity.sub(CHAR_ENTITIES[key], htmlstr, 1)
                sz = re_charEntity.search(htmlstr)
            except KeyError:
                # 以空串代替
                htmlstr = re_charEntity.sub('', htmlstr, 1)
                sz = re_charEntity.search(htmlstr)
        return htmlstr

    # html线性重构
    def line_html(self, html):
        html = re.sub("</?div.*?>|</?table.*?>", "</div><div>", html)
        return html

    # 过滤噪声标签
    def fiter_html(self, html):
        re_meta = re.compile("<meta.*?/?\s*?>", re.I)  # meta
        re_comment = re.compile("<!--[^>]*-->", re.I)  # HTML注释
        re_link = re.compile("<link.*?/?\s*?>", re.I)  # link
        re_script = re.compile('<script[^>]*?>.*?</\s*script\s*>', re.S | re.I)  # script   re.S .匹配任意字符 re.I 忽略大小写
        re_img = re.compile("<img.*?/?\s*?>", re.I)  # img
        re_cdata = re.compile('//<!\[CDATA\[[^>]*//\]\]>', re.I)  # CDATA
        re_style = re.compile('<style[^>]*>[^<]*<\s*/\s*style\s*>', re.I)  # style
        # re_form = re.compile('<form[^>]*?>.*?</\s*form\s*>', re.S | re.I)
        re_blank = re.compile('\n+')  # 空行
        re_br = re.compile('<br\s*?/?>')  # 处理换行
        re_para = re.compile('</p>', re.I)
        re_span = re.compile('<span[^>]*?>')
        html = re.sub(re_meta, "", html)
        html = re.sub(re_comment, "", html)
        html = re.sub(re_link, "", html)
        html = re.sub(re_script, "", html)
        html = re.sub(re_img, "", html)
        html = re.sub(re_cdata, "", html)
        html = re.sub(re_style, "", html)
        # html = re.sub(re_form, "", html)
        html = re.sub(re_br, "\n", html)
        html = re.sub(re_blank, "\n", html)
        html = re.sub(re_para, "</p>\n", html)
        html = re.sub(re_span, '', html)
        return html

    # 计算兴趣度
    def cal_score(self,text):
        if "。" not in text:
            if "，" in text:
                return 0
            else:
                return -1
        else:
            num = text.count("，") + 1
            return num

    # 抽取聚类段落集里的特征
    def extract_feature(self, para_dict):
        # print("抽取段落集特征")
        dict_feature = {}
        index, text = max(para_dict.items(), key=lambda asd: asd[1][1])
        # print(text)
        list_features = re.findall("(<p.*?>)", text[0], re.I)
        set_features = list(set(list_features))
        for each_feature in set_features:
            dict_feature[each_feature] = list_features.count(each_feature)
        feature = max(dict_feature.items(), key=lambda m: m[1])[0]
        # print(feature, index)
        return index, feature

    # 通过计算兴趣度得分，抽取聚类段落集和吸收段落集
    def extract_paragraph(self, html):
        # print(html)
        para1_dict = {}
        para2_dict = {}
        index = -1
        for each_div in re.findall("<div>(.*?)</div>", html, re.S):
            if len(each_div.strip()) == 0:
                continue
            each_para = each_div.strip()
            index += 1
            score = self.cal_score(each_para)
            if score > self.score:
                para1_dict[index] = [each_para, score]
                # print(index,each_para,score)
                # print("_-------------")
            else:
                para2_dict[index] = [each_para, score]
        return para1_dict, para2_dict

    # 聚类段落集聚类生成生成正文脉络集合
    def gen_skeleton(self, para_dict, index, feature):
        skeleton_dict = {}
        num_list = []
        # print("聚类段落集聚类生成生成正文脉络集合")
        # print(para_dict[index][0])
        # 段落向前聚类
        for num in para_dict.keys():
            num_list.append(num)
        od = num_list.index(index)
        f_list = num_list[0:od]
        l_list = num_list[od:len(num_list)]
        # print(f_list, l_list)
        # 向后聚类
        while l_list:
            tmp = l_list.pop(0)
            length = abs(tmp - index)
            if length < self.length:
                if re.match(".*?{0}".format(feature), para_dict[tmp][0], re.S):
                    skeleton_dict[tmp] = para_dict[tmp]
                    # print("向后聚类段落")
                    # print(para_dict[tmp])
            index = tmp
        # 向前聚类
        while f_list:
            tmp = f_list.pop()
            length = abs(index - tmp)
            if length < self.length:
                if re.match(".*?{0}".format(feature), para_dict[tmp][0], re.S):
                    skeleton_dict[tmp] = para_dict[tmp]
                    # print("向前聚类段落")
                    # print(para_dict[tmp])
            index = tmp
        return skeleton_dict

    def absorb_text(self, skeleton_dict, para_dict):
        content_dict = skeleton_dict
        sk_list = skeleton_dict.keys()
        pa_list = para_dict.keys()
        sk_list = sorted(sk_list)
        pa_list = sorted(pa_list)
        pa1_list = []
        pa2_list = []
        pa3_list = []
        # print(sk_list)
        # print(pa_list)
        for each in pa_list:
            if each < sk_list[0]:
                pa1_list.append(each)
            if each > sk_list[-1]:
                pa3_list.append(each)
            if (each >= sk_list[0]) and (each <= sk_list[-1]):
                pa2_list.append(each)
        # print(pa1_list, pa2_list, pa3_list)
        while pa1_list:
            tmp = pa1_list.pop()
            index = sk_list[0]
            if abs(tmp - index) < self.length:
                if para_dict[tmp][1] * 2 > self.score:
                    content_dict[tmp] = para_dict[tmp]
            else:
                break
        while pa3_list:
            tmp = pa3_list.pop(0)
            index = sk_list[-1]
            if abs(tmp - index) < self.length:
                if para_dict[tmp][1] * 2 > self.score:
                    content_dict[tmp] = para_dict[tmp]
            else:
                break
        while pa2_list:
            tmp = pa2_list.pop()
            if para_dict[tmp][1] * 2 > self.score:
                content_dict[tmp] = para_dict[tmp]
        content_list = content_dict.keys()
        content_list = sorted(content_list)
        contents = []
        for each in content_list:
            contents.append(content_dict[each][0])
        text = "".join(contents)
        text = re.sub("<p.*?>", "\t", text, re.I)
        text = re.sub("</p.*?>", "\n", text, re.I)
        text = re.sub("\n+", "\n", text)
        text = re.sub("<.*?>", "", text)
        return text

    # 正文脉络集合,吸收伪噪声段落集,生成正文
    def run(self, url):
        body = {}
        contents = []
        html = self.get_html(url)
        title = self.get_title(html)
        next_urls = []
        next_urls.append(url)
        index = 0
        while True:
            index += 1
            if index > 10:
                break
            tag, next_url = self.get_next_url(html)
            # print(next_url)
            if next_url == next_urls[-1]:
                break
            else:
                next_urls.append(next_url)
            html = self.line_html(html)
            html = self.fiter_html(html)
            html = self.replace_char_entity(html)
            para1_dcit, para2_dict = self.extract_paragraph(html)
            skeleton_dict = {}
            if para1_dcit:
                index, feature = self.extract_feature(para1_dcit)
                skeleton_dict = self.gen_skeleton(para1_dcit, index, feature)
            if para2_dict and skeleton_dict:
                contents.append(self.absorb_text(skeleton_dict, para2_dict))
            if not tag:
                break
            try:
                html = self.get_html(next_url)
            except:
                print("error")
                break

        content = "\n".join(contents)
        body["title"] = title
        body["content"] = content
        return body

if __name__ == "__main__":
    spider = ExtractContent()
    url = "http://news.xinhuanet.com/world/2017-05/04/c_129588259.htm"
    # url = "http://www.cankaoxiaoxi.com/roll10/bd/20170505/1963802.shtml"
    # url = "http://society.huanqiu.com/article/2017-05/10616083.html?from=bdwz"
    # url = "http://xinwen.eastday.com/a/n170508065403913.html"
    url = "http://news.china.com/domestic/945/20170508/30497892.html"
    url = "http://news.china.com/domestic/945/20170508/30500647.html"
    url = "http://www.cankaoxiaoxi.com/roll10/bd/20170508/1971194.shtml"
    url = "http://xinwen.eastday.com/a/n170508122355025.html"
    url = "http://news.ifeng.com/a/20170508/51059222_0.shtml?_zbs_baidu_news"
    url = "http://www.cankaoxiaoxi.com/roll10/bd/20170508/1969781.shtml"
    url = "http://news.cnstock.com/news,bwkx-201705-4073723.htm"
    url = "http://finance.ifeng.com/a/20150703/13815044_0.shtml"
    url = 'http://hk.jrj.com.cn/2017/06/30105722678655.shtml'
    url = 'http://finance.jrj.com.cn/biz/2017/07/02090922684358.shtml'
    url = 'http://hk.jrj.com.cn/2017/07/04095922693347.shtml'
    url = 'http://news.xinhuanet.com/politics/2017-07/09/c_1121289651.htm'
    url = 'http://www.cankaoxiaoxi.com/roll10/bd/20170710/2177265.shtml'
    url = 'http://www.cankaoxiaoxi.com/roll10/bd/20170710/2177017.shtml'
    url = "http://news.china.com/domestic/945/20170508/30497892.html"
    body = spider.run(url)
    print(body["title"])
    print(body["content"])
    # for each in re.findall('<a.*?下一页</a>',html):

    # print(html)