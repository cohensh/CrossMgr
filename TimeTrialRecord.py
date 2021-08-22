import wx
import wx.grid			as gridlib
from wx.lib import masked
from wx.grid import GridCellNumberEditor
import wx.lib.buttons

import math
import Model
import Utils
from ReorderableGrid import ReorderableGrid
from HighPrecisionTimeEdit import HighPrecisionTimeEdit
from PhotoFinish import TakePhoto
from SendPhotoRequests import SendRenameRequests
import OutputStreamer

def formatTime( secs ):
	return Utils.formatTime(
		secs,
		highPrecision=True,		extraPrecision=True,
		forceHours=True, 		twoDigitHours=True,
	)

def StrToSeconds( tStr ):
	secs = Utils.StrToSeconds( tStr )
	# Make sure we don't lose the last decimal accuracy.
	if int(secs*1000.0) + 1 == int((secs + 0.0001)*1000.0):
		secs += 0.0001
	return secs
	
class HighPrecisionTimeEditor(gridlib.GridCellEditor):
	Empty = '00:00:00.000'
	def __init__(self):
		self._tc = None
		self.startValue = self.Empty
		super().__init__()
		
	def Create( self, parent, id = wx.ID_ANY, evtHandler = None ):
		self._tc = HighPrecisionTimeEdit(parent, id, allow_none = False, style = wx.TE_PROCESS_ENTER)
		self.SetControl( self._tc )
		if evtHandler:
			self._tc.PushEventHandler( evtHandler )
	
	def SetSize( self, rect ):
		self._tc.SetSize(rect.x, rect.y, rect.width+2, rect.height+2, wx.SIZE_ALLOW_MINUS_ONE )
	
	def BeginEdit( self, row, col, grid ):
		self.startValue = grid.GetTable().GetValue(row, col).strip()
		self._tc.SetValue( self.startValue )
		self._tc.SetFocus()
		
	def EndEdit( self, row, col, grid, value = None ):
		changed = False
		val = self._tc.GetValue()
		if val != self.startValue:
			if val == self.Empty:
				val = ''
			changed = True
			grid.GetTable().SetValue( row, col, val )
		self.startValue = self.Empty
		self._tc.SetValue( self.startValue )
		
	def Reset( self ):
		self._tc.SetValue( self.startValue )
		
	def Clone( self ):
		return HighPrecisionTimeEditor()

class TimeTrialRecord( wx.Panel ):
	def __init__( self, parent, controller, id = wx.ID_ANY ):
		super().__init__(parent, id)
		self.SetBackgroundColour( wx.WHITE )

		self.controller = controller

		self.headerNames = [_('Time'), '   {}   '.format(_('Bib'))]
		
		fontSize = 18
		self.font = wx.Font( (0,fontSize), wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL )
		self.bigFont = wx.Font( (0,int(fontSize*1.30)), wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL )
		self.vbs = wx.BoxSizer(wx.VERTICAL)
		
		tapForTimeLabel = _('Tap for Time')
		if 'WXMAC' in wx.Platform:
			self.recordTimeButton = wx.lib.buttons.ThemedGenButton( self, label=tapForTimeLabel )
			self.recordTimeButton.Bind( wx.EVT_BUTTON, self.doRecordTime )
		else:
			self.recordTimeButton = wx.Button( self, label=tapForTimeLabel )
			self.recordTimeButton.Bind( wx.EVT_LEFT_DOWN, self.doRecordTime )
		
		self.recordTimeButton.SetFont( self.bigFont )
		
		self.recordTimeButton.SetToolTip( wx.ToolTip('\n'.join([
				_('Tap to get a Time, or press "t".'),
				_('Then enter the Bib number(s) and Save.')
			])) )
			
		tapExplain = wx.StaticText( self, label=_('(or press "t")') )
		tapExplain.SetFont( self.font )
		
		hbs = wx.BoxSizer( wx.HORIZONTAL )
		hbs.Add( self.recordTimeButton, 0 )
		hbs.Add( tapExplain, flag=wx.ALIGN_CENTRE_VERTICAL|wx.LEFT, border=20 )
		
		self.grid = ReorderableGrid( self, style = wx.BORDER_SUNKEN )
		self.grid.SetFont( self.font )
		self.grid.EnableReorderRows( False )
		self.grid.DisableDragColSize()
		self.grid.DisableDragRowSize()

		dc = wx.WindowDC( self.grid )
		dc.SetFont( self.font )
		width, height = dc.GetTextExtent(' 999 ')
		self.rowLabelSize = width
		self.grid.SetRowLabelSize( self.rowLabelSize )
		
		self.grid.CreateGrid( 0, len(self.headerNames) )
		self.grid.Bind( gridlib.EVT_GRID_LABEL_LEFT_CLICK, self.doClickLabel )
		for col, name in enumerate(self.headerNames):
			self.grid.SetColLabelValue( col, name )
		self.grid.SetLabelFont( self.font )
		for col in range(self.grid.GetNumberCols()):
			attr = gridlib.GridCellAttr()
			attr.SetFont( self.font )
			if col == 0:
				attr.SetEditor( HighPrecisionTimeEditor() )
			elif col == 1:
				attr.SetRenderer( gridlib.GridCellNumberRenderer() )
				attr.SetEditor( GridCellNumberEditor() )
			self.grid.SetColAttr( col, attr )
		
		saveExplain = wx.StaticText( self, label=_('(or press "s")') )
		saveExplain.SetFont( self.font )
		saveLabel = _('Save')
		if 'WXMAC' in wx.Platform:
			self.commitButton = wx.lib.buttons.ThemedGenButton( self, label=saveLabel )
		else:
			self.commitButton = wx.Button( self, label=saveLabel )
		self.commitButton.Bind( wx.EVT_BUTTON, self.doCommit )
		self.commitButton.SetFont( self.bigFont )
		self.commitButton.SetToolTip(wx.ToolTip(_('Save Entries (or press "s")')))
		
		hbsCommit = wx.BoxSizer( wx.HORIZONTAL )
		hbsCommit.Add( saveExplain, flag=wx.ALIGN_CENTRE_VERTICAL|wx.RIGHT, border=20 )
		hbsCommit.Add( self.commitButton, 0 )
		
		self.vbs.Add( hbs, 0, flag=wx.ALL, border = 4 )
		self.vbs.Add( self.grid, 1, flag=wx.ALL|wx.EXPAND, border = 4 )
		self.vbs.Add( hbsCommit, 0, flag=wx.ALL|wx.ALIGN_RIGHT, border = 4 )
		
		idRecordAcceleratorId, idCommitAccelleratorId = wx.NewId(), wx.NewId()
		self.Bind(wx.EVT_MENU, self.doRecordTime, id=idRecordAcceleratorId)
		self.Bind(wx.EVT_MENU, self.doCommit, id=idCommitAccelleratorId)
		accel_tbl = wx.AcceleratorTable([
			(wx.ACCEL_NORMAL,  ord('T'), idRecordAcceleratorId),
			(wx.ACCEL_NORMAL,  ord('S'), idCommitAccelleratorId),
		])
		self.SetAcceleratorTable(accel_tbl)
		
		self.SetSizer(self.vbs)
		self.Fit()
		
	def doClickLabel( self, event ):
		if event.GetCol() == 0:
			self.doRecordTime( event )
	
	def doRecordTime( self, event ):
		t = Model.race.curRaceTime()
		
		# Trigger the camera.
		with Model.LockRace() as race:
			if not race:
				return
			if race.enableUSBCamera:
				race.photoCount += TakePhoto( 0, StrToSeconds(formatTime(t)) )
	
		# Grow the table to accomodate the next entry.
		Utils.AdjustGridSize( self.grid, rowsRequired=self.grid.GetNumberRows()+1 )			
		self.grid.SetCellValue( self.grid.GetNumberRows()-1, 0, formatTime(t) )
		
		# Set the edit cursor at the first empty bib position.
		for row in range(self.grid.GetNumberRows()):
			text = self.grid.GetCellValue(row, 1)
			if not text or text == '0':
				self.grid.SetGridCursor( row, 1 )
				break
		
	def doCommit( self, event ):
		self.grid.SetGridCursor( 0, 0, )
	
		# Find the last row without a time.
		timesBibs = []
		timesNoBibs = []
		for row in range(self.grid.GetNumberRows()):
			tStr = self.grid.GetCellValue(row, 0).strip()
			if not tStr:
				continue
			
			bib = self.grid.GetCellValue(row, 1).strip()
			try:
				bib = int(bib)
			except (TypeError, ValueError):
				bib = 0
			
			if bib:
				timesBibs.append( (tStr, bib) )
			else:
				timesNoBibs.append( tStr )
				
		for row in range(self.grid.GetNumberRows()):
			for column in range(self.grid.GetNumberCols()):
				self.grid.SetCellValue(row, column, '' )
		
		if timesBibs and Model.race:
			with Model.LockRace() as race:
				bibRaceSeconds = []
				
				for tStr, bib in timesBibs:
					raceSeconds = StrToSeconds(tStr)
					race.addTime( bib, raceSeconds )
					OutputStreamer.writeNumTime( bib, raceSeconds )
					bibRaceSeconds.append( (bib, raceSeconds) )
				
			wx.CallAfter( Utils.refresh )
		
		Utils.AdjustGridSize( self.grid, rowsRequired=0 )
	
	def refresh( self ):
		self.grid.AutoSizeRows()
		
		dc = wx.WindowDC( self.grid )
		dc.SetFont( self.font )
		
		widthTotal = self.rowLabelSize
		width, height = dc.GetTextExtent(" 00:00:00.000 ")
		self.grid.SetColSize( 0, width )
		widthTotal += width
		
		width, height = dc.GetTextExtent(" 9999 ")
		self.grid.SetColSize( 1, width )
		widthTotal += width
		
		scrollBarWidth = 48
		self.grid.SetSize( (widthTotal + scrollBarWidth, -1) )
		self.GetSizer().SetMinSize( (widthTotal + scrollBarWidth, -1) )
		
		self.grid.ForceRefresh()
		self.GetSizer().Layout()
		
		wx.CallAfter( self.recordTimeButton.SetFocus )
		
	def commit( self ):
		pass
		
if __name__ == '__main__':
	Utils.disable_stdout_buffering()
	app = wx.App(False)
	mainWin = wx.Frame(None,title="CrossMan", size=(600,600))
	Model.setRace( Model.Race() )
	Model.getRace()._populate()
	timeTrialRecord = TimeTrialRecord(mainWin, None)
	timeTrialRecord.refresh()
	mainWin.Show()
	app.MainLoop()
