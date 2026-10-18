# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Reviewed data-only Python adapter; no eval, shell or model dependency."""
import csv
import io
import math

CSV_SCHEMA=dict(type='object',additionalProperties=False,required=['column'],properties=dict(
    column=dict(type='string',title='Numeric column',minLength=1,maxLength=120),
    delimiter=dict(type='string',title='Delimiter',enum=[',',';','\t'],default=',')))


def csv_adapter(raw,inputs,folder,token):
    if token.is_cancelled:raise ValueError('LIBRARY_CANCELLED')
    return csv_summary(raw,inputs)


def csv_summary(raw,inputs):
    if not isinstance(inputs,dict) or set(inputs)-{'column','delimiter'}:raise ValueError('CSV_INPUT_CONTRACT_INVALID')
    column=inputs.get('column');delimiter=inputs.get('delimiter',',')
    if not isinstance(column,str) or not 1<=len(column)<=120 or delimiter not in {',',';','\t'}:
        raise ValueError('CSV_COLUMN_OR_DELIMITER_INVALID')
    if not isinstance(raw,bytes) or not raw or len(raw)>5*1024*1024:raise ValueError('CSV_BYTE_LIMIT')
    stream=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=delimiter)
    if not stream.fieldnames or len(set(stream.fieldnames))!=len(stream.fieldnames) or column not in stream.fieldnames:
        raise ValueError('CSV_COLUMN_MISSING_OR_DUPLICATE')
    count=0;total=0.;low=None;high=None;missing=0;invalid=0;rows=0
    for row in stream:
        rows+=1
        if rows>100000:raise ValueError('CSV_ROW_LIMIT')
        text=row.get(column)
        if text is None or not text.strip():missing+=1;continue
        try:value=float(text)
        except ValueError:invalid+=1;continue
        if not math.isfinite(value):invalid+=1;continue
        count+=1;total+=value;low=value if low is None else min(low,value);high=value if high is None else max(high,value)
    if not count or not math.isfinite(total):raise ValueError('CSV_NO_FINITE_NUMERIC_RESULT')
    return dict(schema_version='csv-summary-1.0',text='Calculated from the attached CSV bytes; no scene or robot change.',
        tables=[dict(title='Numeric summary',columns=['Column','Rows','Numeric','Missing','Invalid','Sum','Mean','Minimum','Maximum'],
            rows=[[column,rows,count,missing,invalid,total,total/count,low,high]])],physical_authority=False)


def read_obj(raw):
    """Static OBJ vertices/face topology only; do not resolve mtl/other paths."""
    if not isinstance(raw,bytes) or not raw or len(raw)>10*1024*1024:raise ValueError('OBJ_BYTE_LIMIT')
    points=[];triangles=[]
    for line in raw.decode('utf-8-sig').splitlines():
        fields=line.split()
        if not fields or fields[0].startswith('#'):continue
        if fields[0]=='v':
            if len(fields)!=4:raise ValueError('OBJ_VERTEX_CONTRACT_INVALID')
            points.append([float(v) for v in fields[1:]])
            if len(points)>12000:raise ValueError('OBJ_VERTEX_LIMIT')
        elif fields[0]=='f':
            if len(fields)!=4:raise ValueError('OBJ_TRIANGULATION_REQUIRED')
            indices=[]
            for field in fields[1:]:
                n=int(field.split('/')[0]);n=n-1 if n>0 else len(points)+n
                if not 0<=n<len(points):raise ValueError('OBJ_INDEX_INVALID')
                indices.append(n)
            triangles.append(indices)
            if len(triangles)>24000:raise ValueError('OBJ_TRIANGLE_LIMIT')
        elif fields[0] in {'mtllib','call','csh','curv','surf'}:
            raise ValueError('OBJ_EXTERNAL_MATERIAL_OR_EXECUTABLE_UNSUPPORTED')
        elif fields[0] not in {'o','g','s','usemtl','vn','vt'}:
            raise ValueError('OBJ_UNSUPPORTED_STATEMENT')
    return points,triangles
