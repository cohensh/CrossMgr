import wx
import wx.grid as gridlib

import os
import io
from html import escape
from urllib.parse import quote
import sys
import urllib
import base64
import datetime

import Utils
import SeriesModel
import GetModelInfo
from ReorderableGrid import ReorderableGrid
from FitSheetWrapper import FitSheetWrapper
import FtpWriteFile
from ExportGrid import tag

import xlwt
import io
import re
import webbrowser
import subprocess
import platform

reNoDigits = re.compile( '[^0-9]' )

HeaderNamesTemplate = ['Pos', 'Team']
def getHeaderNames():
	return HeaderNamesTemplate + ['Points' if SeriesModel.model.scoreByPoints else 'Time', 'Gap']

#----------------------------------------------------------------------------------

def toFloat( n ):
	try:
		return float(n)
	except Exception:
		pass
	try:
		return float(n.split()[0])
	except Exception:
		pass
	try:
		return float(n.split(',')[0])
	except Exception:
		pass
	return -1.0
	
def toSeconds( s ):
	secs = 0.0
	try:
		for f in s.split(':'):
			secs = secs * 60.0 + float(f)
	except Exception:
		return -1.0
	return secs
	
def filterResults( results, scoreByPoints, scoreByTime ):
	if scoreByPoints:
		return [rr for rr in results if toFloat(rr[1]) > 0.0]
	elif scoreByTime:
		return [rr for rr in results if toSeconds(rr[1]) > 0.0]
	return []

def getHeaderGraphicBase64():
	if Utils.mainWin:
		b64 = Utils.mainWin.getGraphicBase64()
		if b64:
			return b64
	graphicFName = os.path.join(Utils.getImageFolder(), 'SeriesMgr128.png')
	with io.open(graphicFName, 'rb') as f:
		return 'data:image/png;base64,{}'.format(base64.standard_b64encode(f.read()))

def formatTeamResults( scoreByPoints, rt ):
	if scoreByPoints:
		# The first value is the team score.  Subsequent values are the individual ranks.
		if not rt[0]:
			return '';
		return '{} ({})'.format(rt[0], Utils.ordinal(rt[1]))
	else:
		rt = [r for r in rt if r.time]
		if not rt:
			return ''
		total = sum( r.time for r in rt )
		if len(rt) == 1:
			r = rt[0]
			return '{}'.format(Utils.formatTime(r.time))
		return '{} = {}'.format(Utils.formatTime(total), '+'.join( '{}'.format(Utils.formatTime(r.time)) for r in rt) )

def getHtmlFileName():
	modelFileName = Utils.getFileName() if Utils.getFileName() else 'Test.smn'
	fileName		= os.path.basename( os.path.splitext(modelFileName)[0] + '-Team.html' )
	defaultPath = os.path.dirname( modelFileName )
	return os.path.join( defaultPath, fileName )
	
def getHtml( htmlfileName=None, seriesFileName=None ):
	model = SeriesModel.model
	scoreByPoints = model.scoreByPoints
	scoreByTime = model.scoreByTime
	bestResultsToConsider = model.bestResultsToConsider
	mustHaveCompleted = model.mustHaveCompleted
	considerPrimePointsOrTimeBonus = model.considerPrimePointsOrTimeBonus
	raceResults = model.extractAllRaceResults( adjustForUpgrades=False, isIndividual=False )
	
	categoryNames = model.getCategoryNamesSortedTeamPublish()
	if not categoryNames:
		return '<html><body>SeriesMgr: No Categories.</body></html>'
	
	HeaderNames = getHeaderNames()
	pointsForRank = { r.getFileName(): r.pointStructure for r in model.races }
	teamPointsForRank = { r.getFileName(): r.teamPointStructure for r in model.races }

	if not seriesFileName:
		seriesFileName = (os.path.splitext(Utils.mainWin.fileName)[0] if Utils.mainWin and Utils.mainWin.fileName else 'Series Results')
	title = os.path.basename( seriesFileName ) + ' Team Results'
	
	pointsStructures = {}
	pointsStructuresList = []
	for race in model.races:
		if race.pointStructure not in pointsStructures:
			pointsStructures[race.pointStructure] = []
			pointsStructuresList.append( race.pointStructure )
		pointsStructures[race.pointStructure].append( race )
	
	html = io.open( htmlfileName, 'w', encoding='utf-8', newline='' )
	
	def write( s ):
		html.write( '{}'.format(s) )
	
	with tag(html, 'html'):
		with tag(html, 'head'):
			with tag(html, 'title'):
				write( title.replace('\n', ' ') )
			with tag(html, 'meta', dict(charset="UTF-8",
										author="Edward Sitarski",
										copyright="Edward Sitarski, 2013-{}".format(datetime.datetime.now().strftime('%Y')),
										generator="SeriesMgr")):
				pass
			with tag(html, 'style', dict( type="text/css")):
				write( '''
body{ font-family: sans-serif; }

h1{ font-size: 250%; }
h2{ font-size: 200%; }

#idRaceName {
	font-size: 200%;
	font-weight: bold;
}
#idImgHeader { box-shadow: 4px 4px 4px #888888; }
.smallfont { font-size: 80%; }
.bigfont { font-size: 120%; }
.hidden { display: none; }

#buttongroup {
	margin:4px;   
	float:left;
}

#buttongroup label {
	float:left;
	margin:4px;
	background-color:#EFEFEF;
	border-radius:4px;
	border:1px solid #D0D0D0;
	overflow:auto;
	cursor: pointer;
}

#buttongroup label span {
	text-align:center;
	padding:8px 8px;
	display:block;
}

#buttongroup label input {
	position:absolute;
	top:-20px;
}

#buttongroup input:checked + span {
	background-color:#404040;
	color:#F7F7F7;
}

#buttongroup .yellow {
	background-color:#FFCC00;
	color:#333;
}

#buttongroup .blue {
	background-color:#00BFFF;
	color:#333;
}

#buttongroup .pink {
	background-color:#FF99FF;
	color:#333;
}

#buttongroup .green {
	background-color:#7FE57F;
	color:#333;
}
#buttongroup .purple {
	background-color:#B399FF;
	color:#333;
}

table.results {
	font-family:"Trebuchet MS", Arial, Helvetica, sans-serif;
	border-collapse:collapse;
}
table.results td, table.results th {
	font-size:1em;
	padding:3px 7px 2px 7px;
	text-align: left;
}
table.results th {
	font-size:1.1em;
	text-align:left;
	padding-top:5px;
	padding-bottom:4px;
	background-color:#7FE57F;
	color:#000000;
	vertical-align:bottom;
}
table.results tr.odd {
	color:#000000;
	background-color:#EAF2D3;
}

.smallFont {
	font-size: 75%;
}

table.results td.leftBorder, table.results th.leftBorder
{
	border-left:1px solid #98bf21;
}

table.results tr:hover
{
	color:#000000;
	background-color:#FFFFCC;
}
table.results tr.odd:hover
{
	color:#000000;
	background-color:#FFFFCC;
}

table.results td.colSelect
{
	color:#000000;
	background-color:#FFFFCC;
}}

table.results td {
	border-top:1px solid #98bf21;
}

table.results td.noborder {
	border-top:0px solid #98bf21;
}

table.results td.rightAlign, table.results th.rightAlign {
	text-align:right;
}

table.results td.leftAlign, table.results th.leftAlign {
	text-align:left;
}

.topAlign {
	vertical-align:top;
}

table.results th.centerAlign, table.results td.centerAlign {
	text-align:center;
}

.ignored {
	color: #999;
	font-style: italic;
}

table.points tr.odd {
	color:#000000;
	background-color:#EAF2D3;
}

.rank {
	color: #999;
	font-style: italic;
}

.points-cell {
	text-align: right;
	padding:3px 7px 2px 7px;
}

hr { clear: both; }

@media print {
	.noprint { display: none; }
	.title { page-break-after: avoid; }
}
''')

			with tag(html, 'script', dict( type="text/javascript")):
				write( '\nvar catMax={};\n'.format( len(categoryNames) ) )
				write( '''
function removeClass( classStr, oldClass ) {
	var classes = classStr.split( ' ' );
	var ret = [];
	for( var i = 0; i < classes.length; ++i ) {
		if( classes[i] != oldClass )
			ret.push( classes[i] );
	}
	return ret.join(' ');
}

function addClass( classStr, newClass ) {
	return removeClass( classStr, newClass ) + ' ' + newClass;
}

function selectCategory( iCat ) {
	for( var i = 0; i < catMax; ++i ) {
		var e = document.getElementById('catContent' + i);
		if( i == iCat || iCat < 0 )
			e.className = removeClass(e.className, 'hidden');
		else
			e.className = addClass(e.className, 'hidden');
	}
}

function sortTable( table, col, reverse ) {
	var tb = table.tBodies[0];
	var tr = Array.prototype.slice.call(tb.rows, 0);
	
	var parseRank = function( s ) {
		if( !s )
			return 999999;
		var fields = s.split( '(' );
		return parseInt( fields[1] );
	}
	
	var cmpPos = function( a, b ) {
		return parseInt( a.cells[0].textContent.trim() ) - parseInt( b.cells[0].textContent.trim() );
	};
	
	var MakeCmpStable = function( a, b, res ) {
		if( res != 0 )
			return res;
		return cmpPos( a, b );
	};
	
	var cmpFunc;
	if( col == 0 || col == 4 || col == 5 ) {		// Pos, Points or Gap
		cmpFunc = cmpPos;
	}
	else if( col >= 6 ) {				// Race Points/Time and Rank
		cmpFunc = function( a, b ) {
			var x = parseRank( a.cells[6+(col-6)*2+1].textContent.trim() );
			var y = parseRank( b.cells[6+(col-6)*2+1].textContent.trim() );
			return MakeCmpStable( a, b, x - y );
		};
	}
	else {								// Rider data field.
		cmpFunc = function( a, b ) {
		   return MakeCmpStable( a, b, a.cells[col].textContent.trim().localeCompare(b.cells[col].textContent.trim()) );
		};
	}
	tr = tr.sort( function (a, b) { return reverse * cmpFunc(a, b); } );
	
	for( var i = 0; i < tr.length; ++i) {
		tr[i].className = (i % 2 == 1) ? addClass(tr[i].className,'odd') : removeClass(tr[i].className,'odd');
		tb.appendChild( tr[i] );
	}
}

var ssPersist = {};
function sortTableId( iTable, iCol ) {
	var upChar = '&nbsp;&nbsp;&#x25b2;', dnChar = '&nbsp;&nbsp;&#x25bc;';
	var isNone = 0, isDn = 1, isUp = 2;
	var id = 'idUpDn' + iTable + '_' + iCol;
	var upDn = document.getElementById(id);
	var sortState = ssPersist[id] ? ssPersist[id] : isNone;
	var table = document.getElementById('idTable' + iTable);
	
	// Clear all sort states.
	var row0Len = table.tBodies[0].rows[0].cells.length;
	for( var i = 0; i < row0Len; ++i ) {
		var idCur = 'idUpDn' + iTable + '_' + i;
		var ele = document.getElementById(idCur);
		if( ele ) {
			ele.innerHTML = '';
			ssPersist[idCur] = isNone;
		}
	}

	if( iCol == 0 ) {
		sortTable( table, 0, 1 );
		return;
	}
	
	++sortState;
	switch( sortState ) {
	case isDn:
		upDn.innerHTML = dnChar;
		sortTable( table, iCol, 1 );
		break;
	case isUp:
		upDn.innerHTML = upChar;
		sortTable( table, iCol, -1 );
		break;
	default:
		sortState = isNone;
		sortTable( table, 0, 1 );
		break;
	}
	ssPersist[id] = sortState;
}
''' )

		with tag(html, 'body'):
			with tag(html, 'table'):
				with tag(html, 'tr'):
					with tag(html, 'td', dict(valign='top')):
						write( '<img id="idImgHeader" src="{}" />'.format(getHeaderGraphicBase64()) )
					with tag(html, 'td'):
						with tag(html, 'h1', {'style': 'margin-left: 1cm;'}):
							write( escape(model.name + ' Team Results') )
						if model.organizer:
							with tag(html, 'h2', {'style': 'margin-left: 1cm;'}):
								write( 'by {}'.format(escape(model.organizer)) )
			with tag(html, 'div', {'id':'buttongroup', 'class':'noprint'} ):
				with tag(html, 'label', {'class':'green'} ):
					with tag(html, 'input', {
							'type':"radio",
							'name':"categorySelect",
							'checked':"true",
							'onclick':"selectCategory(-1);"} ):
						with tag(html, 'span'):
							write( 'All' )
				for iTable, categoryName in enumerate(categoryNames):
					with tag(html, 'label', {'class':'green'} ):
						with tag(html, 'input', {
								'type':"radio",
								'name':"categorySelect",
								'onclick':"selectCategory({});".format(iTable)} ):
							with tag(html, 'span'):
								write( '{}'.format(escape(categoryName)) )
			for iTable, categoryName in enumerate(categoryNames):
				results, races = GetModelInfo.GetCategoryResultsTeam(
					categoryName,
					raceResults,
					pointsForRank,
					teamPointsForRank,
					useMostEventsCompleted=model.useMostEventsCompleted,
					numPlacesTieBreaker=model.numPlacesTieBreaker )
				
				results = filterResults( results, scoreByPoints, scoreByTime )
				
				headerNames = HeaderNames + ['{}'.format(r[1]) for r in races]
				
				with tag(html, 'div', {'id':'catContent{}'.format(iTable)} ):
					write( '<p/>')
					write( '<hr/>')
					
					with tag(html, 'h2', {'class':'title'}):
						write( escape(categoryName) )
					with tag(html, 'table', {'class': 'results', 'id': 'idTable{}'.format(iTable)} ):
						with tag(html, 'thead'):
							with tag(html, 'tr'):
								for iHeader, col in enumerate(HeaderNames):
									colAttr = { 'onclick': 'sortTableId({}, {})'.format(iTable, iHeader) }
									if col in ('Gap',):
										colAttr['class'] = 'noprint'
									with tag(html, 'th', colAttr):
										with tag(html, 'span', dict(id='idUpDn{}_{}'.format(iTable,iHeader)) ):
											pass
										write( '{}'.format(escape(col).replace('\n', '<br/>\n')) )
								for iRace, r in enumerate(races):
									# r[0] = RaceData, r[1] = RaceName, r[2] = RaceURL, r[3] = Race
									with tag(html, 'th', {
											'class':'centerAlign noprint',
											#'onclick': 'sortTableId({}, {})'.format(iTable, len(HeaderNames) + iRace),
										} ):
										with tag(html, 'span', dict(id='idUpDn{}_{}'.format(iTable,len(HeaderNames) + iRace)) ):
											pass
										if r[2]:
											with tag(html,'a',dict(href='{}?raceCat={}'.format(r[2], quote(categoryName.encode('utf8')))) ):
												write( '{}'.format(escape(r[1]).replace('\n', '<br/>\n')) )
										else:
											write( '{}'.format(escape(r[1]).replace('\n', '<br/>\n')) )
										if r[0]:
											write( '<br/>' )
											with tag(html, 'span', {'class': 'smallFont'}):
												write( '{}'.format(r[0].strftime('%b %d, %Y')) )
						with tag(html, 'tbody'):
							for pos, (team, result, gap, rrs) in enumerate(results):
								with tag(html, 'tr', {'class':'odd'} if pos % 2 == 1 else {} ):
									with tag(html, 'td', {'class':'rightAlign'}):
										write( '{}'.format(pos+1) )
									with tag(html, 'td'):
										write( '{}'.format(team or '') )
									with tag(html, 'td', {'class':'rightAlign'}):
										write( '{}'.format(result or '') )
									with tag(html, 'td', {'class':'rightAlign noprint'}):
										write( '{}'.format(gap or '') )
									for rt in rrs:
										with tag(html, 'td', {'class': 'centerAlign noprint'}):
											write( formatTeamResults(scoreByPoints, rt) )
										
			#-----------------------------------------------------------------------------
			if considerPrimePointsOrTimeBonus:
				with tag(html, 'p', {'class':'noprint'}):
					write( 'Bonus Points added to Points for Place.' )
					
			#-----------------------------------------------------------------------------
			if scoreByPoints:
				with tag(html, 'div', {'class':'noprint'} ):
					with tag(html, 'p'):
						pass
					with tag(html, 'hr'):
						pass
					
					with tag(html, 'h2'):
						write( 'Point Structures' )
					with tag(html, 'table' ):
						for ps in pointsStructuresList:
							with tag(html, 'tr'):
								for header in [ps.name, 'Races Scored with {}'.format(ps.name)]:
									with tag(html, 'th'):
										write( header )
							
							with tag(html, 'tr'):
								with tag(html, 'td', {'class': 'topAlign'}):
									write( ps.getHtml() )
								with tag(html, 'td', {'class': 'topAlign'}):
									with tag(html, 'ul'):
										for r in pointsStructures[ps]:
											with tag(html, 'li'):
												write( r.getRaceName() )
						
						with tag(html, 'tr'):
							with tag(html, 'td'):
								pass
							with tag(html, 'td'):
								pass
						
					#-----------------------------------------------------------------------------
					
					with tag(html, 'p'):
						pass
					with tag(html, 'hr'):
						pass
						
					with tag(html, 'h2'):
						write( 'Tie Breaking Rules' )
						
					with tag(html, 'p'):
						write( u"If two or more teams are tied on points, the following rules are applied in sequence until the tie is broken:" )
					isFirst = True
					tieLink = u"if still a tie, use "
					with tag(html, 'ol'):
						if model.useMostEventsCompleted:
							with tag(html, 'li'):
								write( u"{}number of events completed".format( tieLink if not isFirst else "" ) )
								isFirst = False
						if model.numPlacesTieBreaker != 0:
							finishOrdinals = [Utils.ordinal(p+1) for p in range(model.numPlacesTieBreaker)]
							if model.numPlacesTieBreaker == 1:
								finishStr = finishOrdinals[0]
							else:
								finishStr = ', '.join(finishOrdinals[:-1]) + ' then ' + finishOrdinals[-1]
							with tag(html, 'li'):
								write( u"{}number of {} place finishes".format( tieLink if not isFirst else "",
									finishStr,
								) )
								isFirst = False
						with tag(html, 'li'):
							write( u"{}best finish position in most recent event".format(tieLink if not isFirst else "") )
							isFirst = False
					
			#-----------------------------------------------------------------------------
			with tag(html, 'p'):
				with tag(html, 'a', dict(href='http://sites.google.com/site/crossmgrsoftware')):
					write( 'Powered by CrossMgr' )
	
	html.close()

brandText = 'Powered by CrossMgr (sites.google.com/site/crossmgrsoftware)'

textStyle = xlwt.easyxf(
	"alignment: horizontal left;"
	"borders: bottom thin;"
)
numberStyle = xlwt.easyxf(
	"alignment: horizontal right;"
	"borders: bottom thin;"
)
centerStyle = xlwt.easyxf(
	"alignment: horizontal center;"
	"borders: bottom thin;"
)
labelStyle = xlwt.easyxf(
	"alignment: horizontal center;"
    "borders: bottom medium;"
)

class TeamResults(wx.Panel):
	#----------------------------------------------------------------------
	def __init__(self, parent):
		"""Constructor"""
		wx.Panel.__init__(self, parent)
 
		self.categoryLabel = wx.StaticText( self, label='Category:' )
		self.categoryChoice = wx.Choice( self, choices = ['No Categories'] )
		self.categoryChoice.SetSelection( 0 )
		self.categoryChoice.Bind( wx.EVT_CHOICE, self.onCategoryChoice )
		self.statsLabel = wx.StaticText( self, label='   /   ' )
		self.refreshButton = wx.Button( self, label='Refresh' )
		self.refreshButton.Bind( wx.EVT_BUTTON, self.onRefresh )
		self.publishToHtml = wx.Button( self, label='Publish to Html' )
		self.publishToHtml.Bind( wx.EVT_BUTTON, self.onPublishToHtml )
		self.publishToFtp = wx.Button( self, label='Publish to Html with FTP' )
		self.publishToFtp.Bind( wx.EVT_BUTTON, self.onPublishToFtp )
		self.publishToExcel = wx.Button( self, label='Publish to Excel' )
		self.publishToExcel.Bind( wx.EVT_BUTTON, self.onPublishToExcel )
		
		self.postPublishCmdLabel = wx.StaticText( self, label='Post Publish Cmd:' )
		self.postPublishCmd = wx.TextCtrl( self, size=(300,-1) )
		self.postPublishExplain = wx.StaticText( self, label='Command to run after publish.  Use %* for all filenames (eg. "copy %* dirname")' )

		hs = wx.BoxSizer( wx.HORIZONTAL )
		hs.Add( self.categoryLabel, flag=wx.TOP, border=4 )
		hs.Add( self.categoryChoice )
		hs.AddSpacer( 4 )
		hs.Add( self.statsLabel, flag=wx.TOP|wx.LEFT|wx.RIGHT, border=4 )
		hs.AddStretchSpacer()
		hs.Add( self.refreshButton )
		hs.Add( self.publishToHtml, flag=wx.LEFT, border=48 )
		hs.Add( self.publishToFtp, flag=wx.LEFT, border=4 )
		hs.Add( self.publishToExcel, flag=wx.LEFT, border=4 )
		
		hs2 = wx.BoxSizer( wx.HORIZONTAL )
		hs2.Add( self.postPublishCmdLabel, flag=wx.ALIGN_CENTRE_VERTICAL )
		hs2.Add( self.postPublishCmd, flag=wx.ALIGN_CENTRE_VERTICAL )
		hs2.Add( self.postPublishExplain, flag=wx.ALIGN_CENTRE_VERTICAL|wx.LEFT, border=4 )
		
		self.grid = ReorderableGrid( self, style = wx.BORDER_SUNKEN )
		self.grid.DisableDragRowSize()
		self.grid.SetRowLabelSize( 64 )
		self.grid.CreateGrid( 0, len(HeaderNamesTemplate)+2 )
		self.grid.SetRowLabelSize( 0 )
		self.grid.EnableReorderRows( False )
		self.grid.Bind( wx.grid.EVT_GRID_LABEL_LEFT_CLICK, self.doLabelClick )
		self.grid.Bind( wx.grid.EVT_GRID_CELL_RIGHT_CLICK, self.doCellClick )
		self.sortCol = None

		self.setColNames(getHeaderNames())

		sizer = wx.BoxSizer( wx.VERTICAL )
		
		sizer.Add(hs, flag=wx.TOP|wx.LEFT|wx.RIGHT, border = 4 )
		sizer.Add(hs2, flag=wx.ALIGN_RIGHT|wx.TOP|wx.LEFT|wx.RIGHT, border = 4 )
		sizer.Add(self.grid, 1, flag=wx.EXPAND|wx.TOP|wx.ALL, border = 4)
		self.SetSizer(sizer)
	
	def onRefresh( self, event ):
		SeriesModel.model.clearCache()
		self.refresh()
	
	def onCategoryChoice( self, event ):
		try:
			Utils.getMainWin().results.setCategory( self.categoryChoice.GetString(self.categoryChoice.GetSelection()) )
		except AttributeError:
			pass
		wx.CallAfter( self.refresh )
		
	def setCategory( self, catName ):
		self.fixCategories()
		model = SeriesModel.model
		categoryNames = model.getCategoryNamesSortedTeamPublish()
		for i, n in enumerate(categoryNames):
			if n == catName:
				self.categoryChoice.SetSelection( i )
				break
	
	def readReset( self ):
		self.sortCol = None
		
	def doLabelClick( self, event ):
		col = event.GetCol()
		label = self.grid.GetColLabelValue( col )
		if self.sortCol == col:
			self.sortCol = -self.sortCol
		elif self.sortCol == -col:
			self.sortCol = None
		else:
			self.sortCol = col
			
		if not self.sortCol:
			self.sortCol = None
		wx.CallAfter( self.refresh )
	
	def doCellClick( self, event ):
		if not hasattr(self, 'popupInfo'):
			self.popupInfo = [
				('{}...'.format(_('Copy Team to Clipboard')),	wx.NewId(), self.onCopyTeam),
			]
			for p in self.popupInfo:
				if p[2]:
					self.Bind( wx.EVT_MENU, p[2], id=p[1] )

		menu = wx.Menu()
		for i, p in enumerate(self.popupInfo):
			if p[2]:
				menu.Append( p[1], p[0] )
			else:
				menu.AppendSeparator()
		
		self.rowCur, self.colCur = event.GetRow(), event.GetCol()
		self.PopupMenu( menu )
		menu.Destroy()		
	
	def copyCellToClipboard( self, r, c ):
		if wx.TheClipboard.Open():
			# Create a wx.TextDataObject
			do = wx.TextDataObject()
			do.SetText( self.grid.GetCellValue(r, c) )

			# Add the data to the clipboard
			wx.TheClipboard.SetData(do)
			# Close the clipboard
			wx.TheClipboard.Close()
		else:
			wx.MessageBox(u"Unable to open the clipboard", u"Error")		
	
	def onCopyTeam( self, event ):
		self.copyCellToClipboard( self.rowCur, 1 )
	
	def setColNames( self, headerNames ):
		for col, headerName in enumerate(headerNames):
			self.grid.SetColLabelValue( col, headerName )
			attr = gridlib.GridCellAttr()
			if headerName in ('Team',):
				attr.SetAlignment( wx.ALIGN_LEFT, wx.ALIGN_TOP )
			elif headerName in ('Pos', 'Points', 'Gap'):
				attr.SetAlignment( wx.ALIGN_RIGHT, wx.ALIGN_TOP )
			else:
				attr.SetAlignment( wx.ALIGN_CENTRE, wx.ALIGN_TOP )
			
			attr.SetReadOnly( True )
			self.grid.SetColAttr( col, attr )
	
	def getGrid( self ):
		return self.grid
		
	def getTitle( self ):
		return self.showResults.GetStringSelection() + ' Series Results'
	
	def fixCategories( self ):
		model = SeriesModel.model
		categoryNames = model.getCategoryNamesSortedTeamPublish()
		lastSelection = self.categoryChoice.GetStringSelection()
		self.categoryChoice.SetItems( categoryNames )
		iCurSelection = 0
		for i, n in enumerate(categoryNames):
			if n == lastSelection:
				iCurSelection = i
				break
		self.categoryChoice.SetSelection( iCurSelection )
		self.GetSizer().Layout()

	def refresh( self ):
		model = SeriesModel.model
		HeaderNames = getHeaderNames()
		scoreByPoints = model.scoreByPoints
		scoreByTime = model.scoreByTime
		
		self.postPublishCmd.SetValue( model.postPublishCmd )
		
		with wx.BusyCursor() as wait:
			self.raceResults = model.extractAllRaceResults( adjustForUpgrades=False, isIndividual=False )
		
		if not self.raceResults:
			Utils.AdjustGridSize( self.grid, rowsRequired=0 )
			return			
		
		self.fixCategories()
		
		categoryName = self.categoryChoice.GetStringSelection()
		if not categoryName or not (scoreByPoints or scoreByTime):
			Utils.AdjustGridSize( self.grid, rowsRequired=0)
			return
		
		self.grid.ClearGrid()
			
		pointsForRank = { r.getFileName(): r.pointStructure for r in model.races }
		teamPointsForRank = { r.getFileName(): r.teamPointStructure for r in model.races }

		results, races = GetModelInfo.GetCategoryResultsTeam(
			categoryName,
			self.raceResults,
			pointsForRank,
			teamPointsForRank,
			useMostEventsCompleted=model.useMostEventsCompleted,
			numPlacesTieBreaker=model.numPlacesTieBreaker,
		)
		
		results = filterResults( results, scoreByPoints, scoreByTime )
		
		headerNames = HeaderNames + ['{}\n{}'.format(r[1],r[0].strftime('%Y-%m-%d') if r[0] else '') for r in races]
		
		Utils.AdjustGridSize( self.grid, len(results), len(headerNames) )
		self.setColNames( headerNames )
		
		for row, (team, points, gap, rrs) in enumerate(results):
			self.grid.SetCellValue( row, 0, '{}'.format(row+1) )
			self.grid.SetCellValue( row, 1, '{}'.format(team) )
			self.grid.SetCellValue( row, 2, '{}'.format(points) )
			self.grid.SetCellValue( row, 3, '{}'.format(gap) )
			for q, rt in enumerate(rrs):
				self.grid.SetCellValue( row, 4 + q, formatTeamResults(scoreByPoints, rt) )
				
			for c in range( 0, len(headerNames) ):
				self.grid.SetCellBackgroundColour( row, c, wx.WHITE )
				self.grid.SetCellTextColour( row, c, wx.BLACK )
		
		if self.sortCol is not None:
			def getBracketedNumber( v ):
				numberMax = 99999
				if not v:
					return numberMax
				try:
					return int(reNoDigits.sub('', v.split('(')[1]))
				except (IndexError, ValueError):
					return numberMax
				
			data = []
			for r in range(0, self.grid.GetNumberRows()):
				rowOrig = [self.grid.GetCellValue(r, c) for c in range(0, self.grid.GetNumberCols())]
				rowCmp = rowOrig[:]
				rowCmp[0] = int(rowCmp[0])
				rowCmp[4] = Utils.StrToSeconds(rowCmp[4])
				rowCmp[5:] = [getBracketedNumber(v) for v in rowCmp[5:]]
				rowCmp.extend( rowOrig )
				data.append( rowCmp )
			
			if self.sortCol > 0:
				fg = wx.WHITE
				bg = wx.Colour(0,100,0)
			else:
				fg = wx.BLACK
				bg = wx.Colour(255,165,0)
				
			iCol = abs(self.sortCol)
			data.sort( key = lambda x: x[iCol], reverse = (self.sortCol < 0) )
			for r, row in enumerate(data):
				for c, v in enumerate(row[self.grid.GetNumberCols():]):
					self.grid.SetCellValue( r, c, v )
					if c == iCol:
						self.grid.SetCellTextColour( r, c, fg )
						self.grid.SetCellBackgroundColour( r, c, bg )
						if c < 4:
							halign = wx.ALIGN_LEFT
						elif c == 4 or c == 5:
							halign = wx.ALIGN_RIGHT
						else:
							halign = wx.ALIGN_CENTRE
						self.grid.SetCellAlignment( r, c, halign, wx.ALIGN_TOP )
		
		self.statsLabel.SetLabel( '{} / {}'.format(self.grid.GetNumberRows(), GetModelInfo.GetTotalUniqueTeams(self.raceResults)) )
		
		self.grid.AutoSizeColumns( False )
		self.grid.AutoSizeRows( False )
		
		self.GetSizer().Layout()
		
	def onPublishToExcel( self, event ):
		model = SeriesModel.model
		
		scoreByPoints = model.scoreByPoints
		scoreByTime = model.scoreByTime
		scoreByPercent = model.scoreByPercent
		scoreByTrueSkill = model.scoreByTrueSkill
		HeaderNames = getHeaderNames()
		
		if Utils.mainWin:
			if not Utils.mainWin.fileName:
				Utils.MessageOK( self, 'You must save your Series to a file first.', 'Save Series' )
				return
		
		self.raceResults = model.extractAllRaceResults( adjustForUpgrades=False, isIndividual=False )
		
		categoryNames = model.getCategoryNamesSortedTeamPublish()
		if not categoryNames:
			return
			
		pointsForRank = { r.getFileName(): r.pointStructure for r in model.races }
		teamPointsForRank = { r.getFileName(): r.teamPointStructure for r in model.races }
		
		wb = xlwt.Workbook()
		
		for categoryName in categoryNames:
			results, races = GetModelInfo.GetCategoryResultsTeam(
				categoryName,
				self.raceResults,
				pointsForRank,
				teamPointsForRank,
				useMostEventsCompleted=model.useMostEventsCompleted,
				numPlacesTieBreaker=model.numPlacesTieBreaker,
			)
			
			results = filterResults( results, scoreByPoints, scoreByTime )
			
			headerNames = HeaderNames + [r[1] for r in races]
			
			ws = wb.add_sheet( re.sub('[:\\/?*\[\]]', ' ', categoryName) )
			wsFit = FitSheetWrapper( ws )

			fnt = xlwt.Font()
			fnt.name = 'Arial'
			fnt.bold = True
			fnt.height = int(fnt.height * 1.5)
			
			headerStyle = xlwt.XFStyle()
			headerStyle.font = fnt
			
			rowCur = 0
			ws.write_merge( rowCur, rowCur, 0, 8, model.name, headerStyle )
			rowCur += 1
			if model.organizer:
				ws.write_merge( rowCur, rowCur, 0, 8, 'by {}'.format(model.organizer), headerStyle )
				rowCur += 1
			rowCur += 1
			colCur = 0
			ws.write_merge( rowCur, rowCur, colCur, colCur + 4, categoryName, xlwt.easyxf(
																	"font: name Arial, bold on;"
																	) );
				
			rowCur += 2
			for c, headerName in enumerate(headerNames):
				wsFit.write( rowCur, c, headerName, labelStyle, bold = True )
			rowCur += 1
			
			for pos, (team, points, gap, rrs) in enumerate(results):
				wsFit.write( rowCur, 0, pos+1, numberStyle )
				wsFit.write( rowCur, 1, team, textStyle )
				wsFit.write( rowCur, 2, points, numberStyle )
				wsFit.write( rowCur, 3, gap, numberStyle )
				for q, rt in enumerate(rrs):
					wsFit.write( rowCur, 4 + q, formatTeamResults(scoreByPoints, rt), centerStyle )
				rowCur += 1
		
			# Add branding at the bottom of the sheet.
			style = xlwt.XFStyle()
			style.alignment.horz = xlwt.Alignment.HORZ_LEFT
			ws.write( rowCur + 2, 0, brandText, style )
		
		if Utils.mainWin:
			xlfileName = os.path.splitext(Utils.mainWin.fileName)[0] + 'Team.xls'
		else:
			xlfileName = 'ResultsTestTeam.xls'
			
		try:
			wb.save( xlfileName )
			webbrowser.open( xlfileName, new = 2, autoraise = True )
			Utils.MessageOK(self, 'Excel file written to:\n\n   {}'.format(xlfileName), 'Excel Write')
			self.callPostPublishCmd( xlfileName )
		except IOError:
			Utils.MessageOK(self,
						'Cannot write "{}".\n\nCheck if this spreadsheet is open.\nIf so, close it, and try again.'.format(xlfileName),
						'Excel File Error', iconMask=wx.ICON_ERROR )
	
	def onPublishToHtml( self, event ):
		if Utils.mainWin:
			if not Utils.mainWin.fileName:
				Utils.MessageOK( self, 'You must save your Series to a file first.', 'Save Series' )
				return
		
		htmlfileName = getHtmlFileName()
		model = SeriesModel.model
		model.postPublishCmd = self.postPublishCmd.GetValue().strip()

		try:
			getHtml( htmlfileName )
			webbrowser.open( htmlfileName, new = 2, autoraise = True )
			Utils.MessageOK(self, 'Html file written to:\n\n   {}'.format(htmlfileName), 'html Write')
		except IOError:
			Utils.MessageOK(self,
						'Cannot write "%s".\n\nCheck if this file is open.\nIf so, close it, and try again.' % htmlfileName,
						'Html File Error', iconMask=wx.ICON_ERROR )
		self.callPostPublishCmd( htmlfileName )
	
	def onPublishToFtp( self, event ):
		if Utils.mainWin:
			if not Utils.mainWin.fileName:
				Utils.MessageOK( self, 'You must save your Series to a file first.', 'Save Series' )
				return
		
		htmlfileName = getHtmlFileName()
		
		try:
			getHtml( htmlfileName )
		except IOError:
			return
		
		html = io.open( htmlfileName, 'r', encoding='utf-8', newline='' ).read()
		with FtpWriteFile.FtpPublishDialog( self, html=html ) as dlg:
			dlg.ShowModal()
		self.callPostPublishCmd( htmlfileName )
	
	def commit( self ):
		model = SeriesModel.model
		if model.postPublishCmd != self.postPublishCmd.GetValue().strip():
			model.postPublishCmd = self.postPublishCmd.GetValue().strip()
			model.setChanged()

	def callPostPublishCmd( self, fname ):
		self.commit()
		postPublishCmd = SeriesModel.model.postPublishCmd
		if postPublishCmd and fname:
			allFiles = [fname]
			if platform.system() == 'Windows':
				files = ' '.join('""{}""'.format(f) for f in allFiles)
			else:
				files = ' '.join('"{}"'.format(f) for f in allFiles)

			if '%*' in postPublishCmd:
				cmd = postPublishCmd.replace('%*', files)
			else:
				cmd = ' '.join( [postPublishCmd, files] )
			
			try:
				subprocess.check_call( cmd, shell=True )
			except subprocess.CalledProcessError as e:
				Utils.MessageOK( self, '{}\n\n    {}\n{}: {}'.format('Post Publish Cmd Error', e, 'return code', e.returncode), _('Post Publish Cmd Error')  )
			except Exception as e:
				Utils.MessageOK( self, '{}\n\n    {}'.format('Post Publish Cmd Error', e), 'Post Publish Cmd Error'  )
		
########################################################################

class TeamResultsFrame(wx.Frame):
	#----------------------------------------------------------------------
	def __init__(self):
		"""Constructor"""
		wx.Frame.__init__(self, None, title="Results Grid Test", size=(800,600) )
		panel = TeamResults(self)
		panel.refresh()
		self.Show()
 
#----------------------------------------------------------------------
if __name__ == "__main__":
	app = wx.App(False)
	Utils.disable_stdout_buffering()
	model = SeriesModel.model
	files = [
		r'C:\Projects\CrossMgr\ParkAvenue2\2013-06-26-Park Ave Bike Camp Arrowhead mtb 4-r1-.cmn',
	]
	model.races = [SeriesModel.Race(fileName, model.pointStructures[0]) for fileName in files]
	frame = TeamResultsFrame()
	app.MainLoop()
