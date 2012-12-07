/*
 *  GridWindMover_c.h
 *  gnome
 *
 *  Created by Generic Programmer on 12/5/11.
 *  Copyright 2011 __MyCompanyName__. All rights reserved.
 *
 */

#ifndef __GridWindMover_c__
#define __GridWindMover_c__

#include "Basics.h"
#include "TypeDefs.h"
#include "WindMover_c.h"
#include "TimeGridVel.h"


#ifndef pyGNOME
#include "GridVel.h"
#else
#include "GridVel_c.h"
#define TGridVel GridVel_c
#endif


class GridWindMover_c : virtual public WindMover_c {

public:
	
	Boolean 	bShowGrid;
	Boolean 	bShowArrows;
	
	char		fPathName[kMaxNameLen];
	char		fFileName[kPtCurUserNameLen]; // short file name
	//char		fFileName[kMaxNameLen]; // short file name - might want to allow longer names
	
	TimeGridVel	*timeGrid;	//VelocityH		grid; 
	short fUserUnits;
	//float fFillValue;
	float fWindScale;
	float fArrowScale;
	//long fTimeShift;		// to convert GMT to local time
	//Boolean fAllowExtrapolationInTime;
	Boolean fIsOptimizedForStep;

	GridWindMover_c (TMap *owner, char* name);
	GridWindMover_c () {}
	virtual OSErr 		PrepareForModelRun(); 
	virtual OSErr 		PrepareForModelStep(const Seconds&, const Seconds&, bool, int numLESets, int* LESetsSizesList); 
	virtual void 		ModelStepIsDone();
	virtual WorldPoint3D       GetMove(const Seconds& model_time, Seconds timeStep,long setIndex,long leIndex,LERec *theLE,LETYPE leType);

	//virtual Boolean 	VelocityStrAtPoint(WorldPoint3D wp, char *diagnosticStr);
	virtual WorldRect GetGridBounds(){return timeGrid->GetGridBounds();}	
	virtual ClassID 	GetClassID () { return TYPE_GRIDWINDMOVER; }
	virtual Boolean		IAm(ClassID id) { if(id==TYPE_GRIDWINDMOVER) return TRUE; return WindMover_c::IAm(id); }

	OSErr 			get_move(int n, unsigned long model_time, unsigned long step_len, WorldPoint3D* ref, WorldPoint3D* delta, double* windages, short* LE_status, LEType spillType, long spill_ID);
};

#endif
