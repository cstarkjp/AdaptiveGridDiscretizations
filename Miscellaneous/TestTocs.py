import nbformat
import os
import json
import TocTools
import sys

"""
This file, when executed as a Python script, tests that the table of contents 
of the notebooks are all correct, and reports any inconsistency.

Optional arguments :
	--update, the tables of contents are updated.
	--show, the tables of contents are shown
"""

def ListNotebookDirs():
	return [dirname for dirname in os.listdir() if dirname[:10]=="Notebooks_"]
def ListNotebookFiles(dirname):
	filenames_extensions = [os.path.splitext(f) for f in os.listdir(dirname)]
	return [filename for filename,extension in filenames_extensions 
	if extension==".ipynb" and filename!="Summary"]


def UpdateToc(filepath,data,cell,toc,update=False,show=False):
	if not ( ('tags' in cell['metadata'] and 'TOC' in cell['metadata']['tags'])
		or (len(cell['source'])>0 and cell['source'][0]==toc[0])): 
		return False # Not a TOC cell

	# A bit of cleanup
	while toc[-1]=="\n": toc=toc[:-1]
	toc[-1]=toc[-1].rstrip()
	cell['source'][-1] = cell['source'][-1].rstrip()

	if toc==cell['source']:
		return True # No need to update

	print(f"TOC of file {filepath} {'is being updated ' if update else 'needs updating'}")
	if show:
		print("------- Old toc -------\n",*cell['source'])
		print("------- New toc -------\n ",*toc)
	if update:
		cell['source'] = toc
		with open(filepath,'w') as f:
			json.dump(data,f,ensure_ascii=False,indent=1)
	return True

def TestToc(dirname,filename,**kwargs):
	filepath = os.path.join(dirname,filename)+".ipynb"
	with open(filepath, encoding='utf8') as data_file:
		data = json.load(data_file)

	# Test Header
	s = data['cells'][0]['source']
	line0 = s[0].strip()
	line0_ref = (
		"# The HFM library - A fast marching solver with adaptive stencils"
		if dirname=="Notebooks_FMM" else
		"# Adaptive PDE discretizations on cartesian grids")

	if line0!=line0_ref:
		print("directory : ",dirname," file : ",filename,
			" line0 : ",line0," differs from expexted ",line0_ref)

	line1 = s[1].strip()
	line1_ref = {
	'Notebooks_Algo':	"## Volume: Algorithmic tools",
	'Notebooks_Div':	"## Volume: Divergence form PDEs",
	'Notebooks_NonDiv':	"## Volume: Non-divergence form PDEs",
	'Notebooks_FMM':	"",
	'Notebooks_Repro':	"## Volume: Reproducible research",
	}[dirname]

	if line0!=line0_ref:
		print("directory : ",dirname," file : ",filename,
			" line1 : ",line1," differs from expexted ",line1_ref)

	toc = TocTools.displayTOC(dirname+"/"+filename,dirname[10:]).splitlines(True)
	for c in data['cells']:
		if UpdateToc(filepath,data,c,toc,**kwargs): return
	print("directory : ",dirname," file : ",filename, " toc not found")


def TestTocs(dirname,**kwargs):
	filepath = os.path.join(dirname,"Summary.ipynb")
	with open(filepath, encoding='utf8') as data_file:
		data = json.load(data_file)
	toc = TocTools.displayTOCs(dirname[10:],dirname+"/").splitlines(True)
	for c in data['cells']:
		if UpdateToc(filepath,data,c,toc,**kwargs): return
	print("directory : ",dirname," Summary toc not found")

def TestTocss(**kwargs):
	filename = "Summary.ipynb"
	with open(filename, encoding='utf8') as data_file:
		data = json.load(data_file)
	toc = TocTools.displayTOCss().splitlines(True)
	for c in data['cells']:
		if UpdateToc(filename,data,c,toc,**kwargs): return
	print("Main Summary toc not found")


if __name__ == '__main__':
#	TestToc("Notebooks_Algo","Dense")
#	TestTocs("Notebooks_Algo")
#	TestTocss()
	kwargs = {"update":False,"show":False}
	for key in sys.argv[1:]:
		assert key[:2]=="--" and key[2:] in kwargs
		kwargs[key[2:]]=True

	TestTocss(**kwargs)
	for dirname in ListNotebookDirs():
		TestTocs(dirname,**kwargs)
		for filename in ListNotebookFiles(dirname):
			TestToc(dirname,filename,**kwargs)

