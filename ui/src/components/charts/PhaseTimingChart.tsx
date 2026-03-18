'use client';

import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface PhaseData {
    name: string;
    duration: number;
    fullName: string;
}

interface PhaseTimingChartProps {
    data: PhaseData[];
}

export const PhaseTimingChart: React.FC<PhaseTimingChartProps> = ({ data }) => {
    return (
        <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip
                    content={({ active, payload }: any) => {
                        if (active && payload && payload.length) {
                            return (
                                <div className="bg-white p-3 border rounded shadow-lg">
                                    <p className="font-semibold">{payload[0].payload.fullName}</p>
                                    <p className="text-blue-600 font-bold">
                                        {payload[0].value}s
                                    </p>
                                </div>
                            );
                        }
                        return null;
                    }}
                />
                <Bar dataKey="duration" fill="#3b82f6" />
            </BarChart>
        </ResponsiveContainer>
    );
};
