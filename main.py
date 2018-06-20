#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import,
                        division, print_function)

__author__ = 'Marat Yusupov'

import spynner
from optparse import OptionParser
import pyparsing
import re
from lxml import html
from lxml.cssselect import CSSSelector
from urlparse import urlparse
import os
import textwrap
from abpy import Filter


class Brows(object):
    # класс забирает контент с url(блокируя загрузку рекламы)
    # и осуществляет перевод контента в "форматированный" текстя
    def __init__(self, lrules, lua, lh, ljq):
        self.rules = lrules
        self.browser = spynner.Browser(user_agent=lua, ignore_ssl_errors=False,
                                       headers=lh)
        self.browser.load_jquery(ljq)
        self.browser.set_url_filter(self.url_filter_ext)

    def change_a_tag(self, s, l, t):
        bod = re.sub("^\s+|\n|\r|\s+$", '', t.body, re.UNICODE)
        return bod + ' [' + self.browser.get_url_from_path(t.href) + '] '

    def change_ph_tag(s, l, t):
        return t.body + '\n'

    def apply_css_sel(self, indoc, urlhost):
        rlist = self.rules.get_css_list()
        if len(rlist) == 0:
            return indoc
        doc = html.document_fromstring(indoc)
        for (d, rule_str) in rlist:
            if len(d) != 0 and not (d in urlhost):
                #print ("host mismatch ",d in urlhost,d)
                continue
            rule = CSSSelector(rule_str)
            for matched in rule(doc):
                matched.getparent().remove(matched)
        return html.tostring(doc, encoding='unicode')

    def trans_tag(self, ltext, tag, fun):
        aopen, aclose = pyparsing.makeHTMLTags(tag)
        a = aopen + pyparsing.SkipTo(aclose).setResultsName("body") + aclose
        a.setParseAction(fun)
        ltext = a.transformString(ltext)
        return ltext

    def adblock_content(self, lurl):
        url_dom = urlparse(lurl).hostname
        # TODO add option stimeout
        self.browser.load(lurl, load_timeout=120, tries=3)
        # soup = self.browser.soup.encode('utf-8') # при таком парсинге кодировка слетает
        # РЕШЕНИЕ: через QString который превращаем в unicode
        html_str = unicode(self.browser.webframe.toHtml().toUtf8(), encoding="UTF-8")
        html_str = self.apply_css_sel(html_str, url_dom)
        removetext = pyparsing.replaceWith("")
        pyparsing.htmlComment.setParseAction(removetext)
        pyparsing.commonHTMLEntity.setParseAction(pyparsing.replaceHTMLEntity)
        text_str = (pyparsing.htmlComment | pyparsing.commonHTMLEntity).transformString(html_str)

        # text_str = self.apply_css_sel(text_str, url_dom)

        for tag in ["script", "iframe", "style", "noscript"]:
            text_str = self.trans_tag(text_str, tag, removetext)
        anytag = pyparsing.anyOpenTag
        anyclose = pyparsing.anyCloseTag
        anytag.setParseAction(removetext)
        anyclose.setParseAction(removetext)
        # заменяем теги со ccылками
        text_str = self.trans_tag(text_str, "a", self.change_a_tag)
        # теги  h p
        text_str = self.trans_tag(text_str, "h", self.change_ph_tag)
        text_str = self.trans_tag(text_str, "p", self.change_ph_tag)

        text_str = (anytag | anyclose).transformString(text_str)
        repeatednewlines = pyparsing.LineEnd() + pyparsing.OneOrMore(pyparsing.LineEnd())
        repeatednewlines.setParseAction(pyparsing.replaceWith("\n\n"))
        text_str = repeatednewlines.transformString(text_str)
        # print("res:", text.encode('utf-8'))
        return text_str

    def url_filter_ext(self, operation, linurl):
        res = self.rules.match(linurl)
        if(res):
            print (res," res rl",linurl)
            return False
        #print (res," nomatch ",linurl)
        #allow_list = [re.compile("avito\.ru.+", re.UNICODE + re.IGNORECASE),
        #          re.compile("avito\.st.+", re.UNICODE + re.IGNORECASE)]
        #print ("url ",urlparse(linurl).hostname)

        return True


class NiceSave(object):
    #  форматирование текста для вывода
    def __init__(self, lwidth=80, ldownloaddir="./"):
        self.width = lwidth
        self.dir = ldownloaddir
        if not os.path.exists(self.dir):
            print("not os.path")
            os.mkdir(self.dir)

    def filename_from_url(self, lurl):
        (filepath, filename) = os.path.split(urlparse(lurl).path)
        if filename == '':
            filename = 'index'
        return self.dir + urlparse(lurl).hostname + filepath + '/' + filename + '.txt'

    def save(self, lurl, lin):
        fn = self.filename_from_url(lurl)
        if not os.path.exists(os.path.dirname(fn)):
            os.makedirs(os.path.dirname(fn))
        lin = re.sub(chr(160), " ", lin, re.UNICODE )
        lin = re.sub('^[\r\n]+|[\r\n]+$', '', lin, re.UNICODE)
        lin = re.sub('^ +', '', lin, re.UNICODE)

        f = open(fn, 'wb')
        #print ("split [",lin.split('\n')[:2])
        for paragraph in lin.split('\n'):
            wt = textwrap.fill(paragraph, replace_whitespace=False) + '\n'
            f.write(wt.encode('utf-8'))
        f.close()
        return 0


if __name__ == '__main__':

    ua_def = 'Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:32.0) Gecko/20100101 Firefox/32.0'
    head_brow = [("Accept-Encoding", "deflate"),
                 ("Accept-Language", "ru,en;q=0.5"),
                 ("Accept-Charset", "utf-8")]
    rulefile = "ruadlist+easylist.txt"

    usage = 'usage: %prog [-j] [-f "filename"] URL'
    parser = OptionParser(usage)
    parser.add_option("-j", dest="loadjquery", action="store_true", default=False,
                      help="Set if need load jquery(opt spynner_jquery_loaded) ")
    # parser.add_option("-u", dest="ua", action="store", default=ua_def,
    #                   help="User-Agent default: [{0}]".format(ua_def))
    # TODO add header option
    parser.add_option("-f", dest="file", action="store", default=rulefile,
                      help="rule for site(tamplate, format adblock): [{0}]".format(rulefile))

    (options, args) = parser.parse_args()
    if len(args) != 1:
        parser.error("incorrect number of arguments")
        exit(0)

    adblockFilter = Filter(file(options.file))
    url = args[0]
    b = Brows(lrules=adblockFilter, lua=ua_def, lh=head_brow, ljq=options.loadjquery)
    text = b.adblock_content(url)
    ss = NiceSave()
    ss.save(url, text)
    print("Ok. ")
