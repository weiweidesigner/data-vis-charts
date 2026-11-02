import json
import pytest
from playwright.sync_api import sync_playwright
from test_data_table import module


def payload(tmp_path, market='US'):
    path=tmp_path/'catalog.json'
    path.write_text(json.dumps({'instruments':[
        {'symbol':'SPY','asset_type':'etf','detail_url':'https://www.ainvest.com/etfs/ARCA-SPY/'},
        {'symbol':'SPY','asset_type':'stock','detail_url':'https://www.ainvest.com/stocks/NYSE-SPY/'},
        {'symbol':'QQQ','asset_type':'etf','detail_url':'https://www.ainvest.com/etfs/NASDAQ-QQQ/'},
        {'symbol':'AMB','asset_type':'etf','detail_url':'https://www.ainvest.com/etfs/CBOE-AMB/'},
        {'symbol':'AMB','asset_type':'etf','detail_url':'https://www.ainvest.com/etfs/NASDAQ-AMB/'}]}))
    link={'keyField':'symbol','lookup':{'path':str(path),'recordsPath':['instruments'],'keyField':'symbol','urlField':'detail_url','where':{'asset_type':'etf'}}}
    return {'locale':'zh-CN','theme':'dark','financialMarket':market,'columns':[
        {'field':'rank','label':'#','type':'number','role':'index'},
        {'field':'symbol','label':'Ticker','link':link},{'field':'name','label':'ETF','link':link},
        {'field':'change','label':'Change','type':'percent','role':'change'},
        {'field':'fee','label':'费率','type':'percent'}], 'rows':[
        {'rank':1,'symbol':'SPY','name':'SPY name','change':1.25,'fee':.2},
        {'rank':2,'symbol':'QQQ','name':'QQQ name','change':-2,'fee':.1},
        {'rank':3,'symbol':'MISS','name':'No identity','change':0,'fee':.05},
        {'rank':4,'symbol':'AMB','name':'Ambiguous','change':None,'fee':.04}]}


def test_verified_identity_join_keeps_data_and_skips_ambiguous_or_unsafe_links(tmp_path):
    p=payload(tmp_path);c=module.normalize(p)
    assert c['columns'][0]['width']==40 and c['columns'][0]['align']=='left'
    assert c['rows'][1][3]==-2
    assert c['links'][0][1:3]==['https://www.ainvest.com/etfs/ARCA-SPY/']*2
    assert c['links'][1][1]=='https://www.ainvest.com/etfs/NASDAQ-QQQ/'
    assert c['links'][2][1] is None and c['links'][3][1] is None
    assert len(c['linkSources'])==1 and c['linkCoverage'][0]['linkedRows']==2
    for url in ['javascript:alert(1)','https://user:password@www.ainvest.com/','https://www.ainvest.com\\@evil.example/']:
        assert module.safe_link(url) is None
    p.pop('financialMarket')
    with pytest.raises(ValueError,match='explicit financialMarket'):module.normalize(p)
    c=module.normalize({'rows':[{'name':'bad','url':'javascript:alert(1)'}],'columns':[{'field':'name','link':{'urlField':'url'}}]})
    assert c['links']==[[None]]


def test_compact_index_change_semantics_and_hover_links(tmp_path):
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        try:
            for market in ['US','CN','HK']:
                ctx=browser.new_context(viewport={'width':1100,'height':800})
                ctx.route('https://www.ainvest.com/**',lambda r:r.fulfill(body='<title>URL fixture</title>'))
                page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content(module.build_html(module.normalize(payload(tmp_path,market))))
                assert page.locator('th').first.inner_text()=='' and page.locator('th').first.locator('button').count()==0
                cell=page.locator('tr[data-row-index="0"] td').first
                assert cell.bounding_box()['width']<=41
                assert cell.locator('span').bounding_box()['x']-cell.bounding_box()['x']==4
                assert cell.evaluate('(e)=>getComputedStyle(e).fontSize')=='11px'
                up=page.locator('td[data-change=up]').evaluate('(e)=>getComputedStyle(e).color')
                down=page.locator('td[data-change=down]').evaluate('(e)=>getComputedStyle(e).color')
                assert up==('rgb(38, 166, 154)' if market=='US' else 'rgb(239, 83, 80)')
                assert down==('rgb(239, 83, 80)' if market=='US' else 'rgb(38, 166, 154)')
                assert page.locator('td[data-change=neutral]').count()==2
                fee=page.locator('tr[data-row-index="0"] td').nth(4)
                assert fee.get_attribute('data-change') is None
                assert fee.evaluate('(e)=>getComputedStyle(e).color')==page.locator('body').evaluate('(e)=>getComputedStyle(e).color')
                assert page.locator('a.cell-link').count()==4
                anchor=page.locator('tr[data-row-index="0"] a.cell-link').first
                assert anchor.evaluate('(e)=>getComputedStyle(e).textDecorationLine')=='none'
                anchor.hover()
                assert anchor.evaluate('(e)=>getComputedStyle(e).textDecorationStyle')=='dashed'
                assert anchor.evaluate('(e)=>getComputedStyle(e).textDecorationLine')=='underline'
                with ctx.expect_page() as opened:anchor.click()
                popup=opened.value;popup.wait_for_url('https://www.ainvest.com/etfs/ARCA-SPY/')
                assert popup.evaluate('window.opener===null');popup.close()
                page.get_by_role('button',name='Change',exact=True).click()
                assert page.locator('tr[data-row-index]').first.get_attribute('data-row-index')=='0'
                assert page.locator('tr[data-row-index="1"] a').first.get_attribute('href')=='https://www.ainvest.com/etfs/NASDAQ-QQQ/'
                page.set_viewport_size({'width':360,'height':800})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.locator('.fullscreen-button').click();page.wait_for_function('document.fullscreenElement!==null')
                assert page.locator('tr[data-row-index="0"] td').first.bounding_box()['width']<=41
                page.locator('.fullscreen-button').click()
                assert not errors
                ctx.close()
        finally:browser.close()
