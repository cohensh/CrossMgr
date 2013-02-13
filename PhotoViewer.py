import Model
import Utils
import ReadSignOnSheet
from PhotoFinish import getPhotoDirName
import wx
import wx.lib.agw.thumbnailctrl as TC
import os
import re
import types

copy_to_clipboard_xpm = [
"16 15 23 1",
"+ c #769CDA",
": c #DCE6F6",
"X c #3365B7",
"* c #FFFFFF",
"o c #9AB6E4",
"< c #EAF0FA",
"# c #B1C7EB",
". c #6992D7",
"3 c #F7F9FD",
", c #F0F5FC",
"$ c #A8C0E8",
"  c None",
"- c #FDFEFF",
"& c #C4D5F0",
"1 c #E2EAF8",
"O c #89A9DF",
"= c #D2DFF4",
"4 c #FAFCFE",
"2 c #F5F8FD",
"; c #DFE8F7",
"% c #B8CCEC",
"> c #E5EDF9",
"@ c #648FD6",
" .....XX        ",
" .oO+@X#X       ",
" .$oO+X##X      ",
" .%$o........   ",
" .&%$.*=&#o.-.  ",
" .=&%.*;=&#.--. ",
" .:=&.*>;=&.... ",
" .>:=.*,>;=&#o. ",
" .<1:.*2,>:=&#. ",
" .2<1.*32,>:=&. ",
" .32<.*432,>:=. ",
" .32<.*-432,>:. ",
" .....**-432,>. ",
"     .***-432,. ",
"     .......... "
]

reload_xpm = [
"16 16 39 1",
" 	c None",
".	c #000000",
"+	c #F7EFD0",
"@	c #F7EFD1",
"#	c #EED680",
"$	c #C38909",
"%	c #F6ECC9",
"&	c #D1940C",
"*	c #B98208",
"=	c #A59458",
"-	c #D1BC70",
";	c #E9D17B",
">	c #B07C08",
",	c #916608",
"'	c #F3E3A8",
")	c #AE7B0A",
"!	c #F4E4AD",
"~	c #F5E9BC",
"{	c #D8E6D2",
"]	c #B9C9B1",
"^	c #6F9059",
"/	c #C6B26A",
"(	c #D7E5D0",
"_	c #AECCA1",
":	c #557C3B",
"<	c #D3E3CB",
"[	c #D0E1C9",
"}	c #DBE7D6",
"|	c #B9C3B5",
"1	c #BDCEB6",
"2	c #A9C79C",
"3	c #65894C",
"4	c #748C64",
"5	c #668154",
"6	c #669447",
"7	c #58833C",
"8	c #E1EBDC",
"9	c #5E8A41",
"0	c #E0EADB",
"    .           ",
"   .+.          ",
"  .@#$.         ",
" .%##&*.        ",
".%=-;>,,.       ",
"...'#)...       ",
"  .!#).  .....  ",
"  .~#).  .{]^.  ",
"  .#/).  .(_:.  ",
"  .....  .<_:.  ",
"       ...[_:...",
"       .}|12345.",
"        .}__67. ",
"         .8_9.  ",
"          .0.   ",
"           .    "
]

def getRiderName( info ):
	lastName = info.get('LastName','')
	firstName = info.get('FirstName','')
	if lastName:
		if firstName:
			return '%s, %s' % (lastName, firstName)
		else:
			return lastName
	return firstName

def ListDirectory(self, directory, fileExtList):
	"""
	Returns list of file info objects for files of particular extensions.

	:param `directory`: the folder containing the images to thumbnail;
	:param `fileExtList`: a Python list of file extensions to consider.
	"""

	fileList = [os.path.normcase(f) for f in os.listdir(directory)]               
	fileList = [f for f in fileList if os.path.splitext(f)[1] in fileExtList]                          
	fileList = [f for f in fileList
		if os.path.basename(f).startswith(self.filePrefix) and os.path.splitext(f)[1] in ['.jpeg', '.jpg'] ]
	return fileList


class PhotoViewer( wx.Panel ):
	def __init__( self, parent, id = wx.ID_ANY, style = 0, size=(-1,-1) ):
		wx.Panel.__init__(self, parent, id, style=style, size=size )

		self.num = 0
		self.thumbSelected = -1
		self.thumbFileName = ''
		
		self.vbs = wx.BoxSizer(wx.VERTICAL)
		
		hbs = wx.BoxSizer( wx.HORIZONTAL )
		
		self.title = wx.StaticText( self, wx.ID_ANY, '' )
		self.title.SetFont( wx.FontFromPixelSize( wx.Size(0,24), wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL ) )
		
		bitmap = wx.BitmapFromXPMData( reload_xpm )
		self.reloadButton = wx.BitmapButton( self, wx.ID_ANY, bitmap )
		self.Bind(wx.EVT_BUTTON, self.OnReload, self.reloadButton )
		
		bitmap = wx.BitmapFromXPMData( copy_to_clipboard_xpm )
		self.copyToClipboardButton = wx.BitmapButton( self, wx.ID_ANY, bitmap )
		self.Bind(wx.EVT_BUTTON, self.OnCopyToClipboard, self.copyToClipboardButton )
		
		#self.printButton = wx.Button( self, wx.ID_ANY, 'Print...' )
		#self.Bind(wx.EVT_BUTTON, self.OnPrint, self.printButton )
		
		self.closeButton = wx.Button( self, wx.ID_CANCEL, 'Close' )
		self.Bind(wx.EVT_BUTTON, self.OnClose, self.closeButton )
		
		hbs.Add( self.title, 1, flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.EXPAND, border = 4 )
		hbs.Add( self.reloadButton, 0, flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL, border = 4 )
		hbs.Add( self.copyToClipboardButton, 0, flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL, border = 4 )
		#hbs.Add( self.printButton, 0, flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL, border = 4 )
		hbs.Add( self.closeButton, 0, flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL, border = 4 )
		
		self.splitter = wx.SplitterWindow( self, wx.ID_ANY )
		self.thumbs = TC.ThumbnailCtrl( self.splitter, wx.ID_ANY )
		self.thumbs.EnableToolTips( True )
		self.thumbs.SetThumbOutline( TC.THUMB_OUTLINE_FULL )
		self.thumbs._scrolled.filePrefix = '#######################'
		self.thumbs._scrolled.ListDirectory = types.MethodType(ListDirectory, self.thumbs._scrolled)
		self.mainPhoto = wx.StaticBitmap( self.splitter, wx.ID_ANY, style = wx.BORDER_SUNKEN, size=(600,500) )
		
		self.splitter.SplitVertically( self.thumbs, self.mainPhoto, 180 )
		self.splitter.SetMinimumPaneSize( 140 )
		self.splitter.UpdateSize()
		
		self.vbs.Add( hbs, proportion=0, flag=wx.EXPAND )
		self.vbs.Add( self.splitter, proportion=1, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM|wx.EXPAND, border = 4 )
		
		self.Bind( wx.EVT_SIZE, self.OnResize )
		self.thumbs.Bind(TC.EVT_THUMBNAILS_SEL_CHANGED, self.OnSelChanged)
		
		self.SetSizer(self.vbs)
		self.vbs.SetSizeHints(self)

	def OnResize( self, event ):
		self.drawMainPhoto()
		event.Skip()
		
	def OnSelChanged(self, event = None):
		self.thumbSelected = self.thumbs.GetSelection()
		try:
			self.thumbFileName = self.thumbs.GetSelectedItem(0).GetFullFileName()
		except:
			self.thumbFileName = ''
		self.drawMainPhoto()
		if event:
			event.Skip()
		
	def OnClose( self, event ):
		if self.GetParent():
			self.GetParent().Show( False )
			
	def OnReload( self, event ):
		self.refresh()
		
	def OnCopyToClipboard( self, event ):
		try:
			bitmap = wx.Bitmap( self.thumbFileName, wx.BITMAP_TYPE_JPEG )
		except:
			return
		d = wx.BitmapDataObject( bitmap )
		if wx.TheClipboard.Open(): 
			wx.TheClipboard.SetData( d ) 
			wx.TheClipboard.Flush() 
			wx.TheClipboard.Close() 
			Utils.MessageOK( self, 'Photo copied to Clipboard.\nYou can now paste it into another program.', 'Copy Succeeded' )
		else: 
			Utils.MessageOK( self, 'Unable to copy photo to Clipboard.', 'Copy Failed', iconMask = wx.ICON_ERROR )
		
	def OnPrint( self, event ):
		try:
			bitmap = wx.Bitmap( self.thumbFileName, wx.BITMAP_TYPE_JPEG )
		except:
			Utils.MessageOK( 'No Photo Available.', 'Print Failed', iconMask = wx.ICON_ERROR )
			return
		
		data = wx.PrintDialogData()
		data.EnableSelection(False)
		data.EnablePrintToFile(True)
		data.EnablePageNumbers(False)
		data.SetMinPage(1)
		data.SetMaxPage(1)
		data.SetAllPages(True)
		#data.SetOrientation(wx.LANDSCAPE)
		dlg = wx.PrintDialog( self, data )
		
		if dlg.ShowModal() == wx.ID_OK:
			dc = dlg.GetPrintDC()
			
			image = bitmap.ConvertToImage()
			
			wDC, hDC = dc.GetSize()
			border = min(wDC, hDC) // 20
			wPhoto, hPhoto = wDC - border * 2, hDC - (3 * border) // 2
			wImage, hImage = image.GetSize()
			
			ratio = min( float(wPhoto) / float(wImage), float(hPhoto) / float(hImage) )
			image.Rescale( int(wImage * ratio), int(hImage * ratio), wx.IMAGE_QUALITY_HIGH )
			if dc.GetDepth() == 8:
				image = image.ConvertToGreyscale()
			
			fontHeight = int(border/2 - border/10)
			font = wx.FontFromPixelSize( wx.Size(0,fontHeight), wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL )
			dc.DrawText( self.title.GetLabel(), border, border )
			bitmap = image.ConvertToBitmap( dc.GetDepth() )
			dc.DrawBitmap( bitmap, border, (3 * border) // 2 )
			dc.EndDoc()
		
		dlg.Destroy()
		Utils.MessageOK( 'Print Succeded.', 'Print Succeded' )
		
	def drawMainPhoto( self ):
		if not self.thumbFileName:
			self.mainPhoto.SetBitmap( wx.NullBitmap )
			return
			
		try:
			bitmap = wx.Bitmap( self.thumbFileName, wx.BITMAP_TYPE_JPEG )
		except:
			self.mainPhoto.SetBitmap( wx.NullBitmap )
			return
			
		depth = bitmap.GetDepth()
		image = bitmap.ConvertToImage()
		bitmap = None
		
		wPhoto, hPhoto = self.mainPhoto.GetSize()
		wImage, hImage = image.GetSize()
		
		ratio = min( float(wPhoto) / float(wImage), float(hPhoto) / float(hImage) )
		image = image.Rescale( int(wImage * ratio), int(hImage * ratio), wx.IMAGE_QUALITY_HIGH )
		image = image.Resize( (wPhoto, hPhoto), (0,0), 255, 255, 255 )
		
		self.mainPhoto.SetBitmap( image.ConvertToBitmap(depth) )
		
	def OnPhotoViewer( self, event ):
		self.OnDoPhotoViewer()
		
	def OnClosePhotoViewer( self, event ):
		self.clear()
		
	def OnDoPhotoViewer( self, event = None ):
		self.refresh()

	def setNumSelect( self, num ):
		if self.num != num:
			self.refresh( num )
		
	def clear( self ):
		self.title.SetLabel( '' )
		self.thumbs._scrolled.filePrefix = '##############'
		self.thumbs.ShowDir( '.' )
		
	def refresh( self, num = None ):
		if num:
			self.num = num
		
		with Model.LockRace() as race:
			if race is None or not self.num:
				self.clear()
				return
				
			# Be smart about refreshing the screen as it is expensive to re-read all the thumbnails.
			# If we are not given 
			if not num and race.isRunning():
				tLast, rLast = race.getLastKnownTimeRider()
				if rLast and rLast.num != self.num:
					return
				
			try:
				externalInfo = race.excelLink.read()
			except AttributeError:
				externalInfo = {}
				
		info = externalInfo.get(self.num, {})
		name = getRiderName( info )
		if info.get('Team', ''):
			name = '%s    (%s)' % (name, info.get('Team', ''))
		self.title.SetLabel( '%d    %s' % (self.num, name) )
		
		if Utils.mainWin and Utils.mainWin.fileName:
			dir = getPhotoDirName( Utils.mainWin.fileName )
		else:
			dir = r'C:\Users\Edward Sitarski\Documents\2013-02-07-test-r1-_Photos'
		
		self.thumbs._scrolled.filePrefix = 'bib-%04d' % self.num
		self.thumbs.ShowDir( dir )
		
		try:
			self.thumbs.SetSelection( self.thumbs.GetItemCount() - 1 )
			self.OnSelChanged()
		except:
			self.clear()
	
class PhotoViewerDialog( wx.Dialog ):
	def __init__(
			self, parent, ID, title='Photo Viewer', size=wx.DefaultSize, pos=wx.DefaultPosition, 
			style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER ):

		# Instead of calling wx.Dialog.__init__ we precreate the dialog
		# so we can set an extra style that must be set before
		# creation, and then we create the GUI object using the Create
		# method.
		pre = wx.PreDialog()
		#pre.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
		pre.Create(parent, ID, title, pos, size, style)

		# This next step is the most important, it turns this Python
		# object into the real wrapper of the dialog (instead of pre)
		# as far as the wxPython extension is concerned.
		self.PostCreate(pre)

		# Now continue with the normal construction of the dialog
		# contents
		sizer = wx.BoxSizer(wx.VERTICAL)

		self.photoViewer = PhotoViewer( self, wx.ID_ANY, size=(600,400) )
		sizer.Add(self.photoViewer, 1, wx.ALIGN_CENTRE|wx.ALL|wx.EXPAND, 5)
		
		self.SetSizer(sizer)
		sizer.Fit(self)

	def refresh( self, num = None ):
		self.photoViewer.refresh( num )
		
	def setNumSelect( self, num ):
		self.photoViewer.setNumSelect( num )
		
if __name__ == '__main__':
	race = Model.newRace()
	race._populate()

	app = wx.PySimpleApp()
	mainWin = wx.Frame(None,title="CrossMan", size=(600,400))
	mainWin.Show()
	photoDialog = PhotoViewerDialog( mainWin, wx.ID_ANY, "PhotoViewer", size=(600,400) )
	photoDialog.photoViewer.setNumSelect( 17 )
	photoDialog.refresh()
	photoDialog.Show()
	app.MainLoop()
