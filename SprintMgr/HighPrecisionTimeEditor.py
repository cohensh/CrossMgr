import wx
import wx.grid as gridlib
import Utils
from HighPrecisionTimeEdit import HighPrecisionTimeEdit

class HighPrecisionTimeEditor(gridlib.GridCellEditor):
	Empty = '00:00:00.000'
	def __init__(self):
		self._tc = None
		self.startValue = self.Empty
		gridlib.GridCellEditor.__init__(self)
		
	def Create( self, parent, id=wx.ID_ANY, evtHandler=None ):
		self._tc = HighPrecisionTimeEdit(parent, id, allow_none=False, style=wx.TE_PROCESS_ENTER)
		self.SetControl( self._tc )
		if evtHandler:
			self._tc.PushEventHandler( evtHandler )
	
	def SetSize( self, rect ):
		self._tc.SetDimensions(rect.x, rect.y, rect.width+2, rect.height+2, wx.SIZE_ALLOW_MINUS_ONE )
	
	def BeginEdit( self, row, col, grid ):
		self.startValue = grid.GetTable().GetValue(row, col).strip()
		v = self.startValue
		v = Utils.SecondsToStr( Utils.StrToSeconds(v), full=True )
		self._tc.SetValue( v )
		self._tc.SetSelection(-1,-1)
		wx.CallAfter( self._tc.SetFocus )
		
	def EndEdit( self, row, col, grid, value = None ):
		changed = False
		v = self._tc.GetValue()
		v = Utils.SecondsToStr( Utils.StrToSeconds(v), full=True )
		if v != self.startValue:
			if v == self.Empty:
				v = ''
			else:
				v = Utils.SecondsToStr( Utils.StrToSeconds(v), full=False )
			changed = True
			grid.GetTable().SetValue( row, col, v )
		self.startValue = self.Empty
		self._tc.SetValue( self.startValue )
		
	def Reset( self ):
		self._tc.SetValue( self.startValue )
		
	def Clone( self ):
		return HighPrecisionTimeEditor()

